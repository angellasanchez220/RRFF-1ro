from fastapi import APIRouter, Header, HTTPException, Body, File, UploadFile
from fastapi.responses import StreamingResponse
import io
import math
from datetime import datetime
from decimal import Decimal
import pandas as pd
from sqlalchemy import text

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()

def _require_admin(authorization: str):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden gestionar el catálogo de materiales")
    return payload


@router.get("")
def list_materiales(search: str = None, categoria: str = None, solo_activos: bool = False):
    """Retorna la lista de materiales e insumos de maquila (etiquetas, mangas, etc.)."""
    with engine.connect() as conn:
        try:
            query = "SELECT * FROM materiales_maquila WHERE 1=1"
            params = {}
            if solo_activos:
                query += " AND activo = TRUE"
            if categoria and categoria.strip() and categoria.upper() != "ALL":
                query += " AND UPPER(categoria) = :cat"
                params["cat"] = categoria.strip().upper()
            if search and search.strip():
                query += " AND (UPPER(sku) LIKE :s OR UPPER(nombre) LIKE :s OR UPPER(COALESCE(descripcion,'')) LIKE :s)"
                params["s"] = f"%{search.strip().upper()}%"
                
            query += " ORDER BY sku ASC"
            df = pd.read_sql(text(query), conn, params=params)
            
            # Formatear fechas y tipos
            if not df.empty:
                df["stock_actual"] = df["stock_actual"].fillna(0).astype(float)
                if "costo_unitario" in df.columns:
                    df["costo_unitario"] = df["costo_unitario"].fillna(0).astype(float)
                df["fecha_creacion"] = df["fecha_creacion"].astype(str)
                df["fecha_actualizacion"] = df["fecha_actualizacion"].astype(str)
                data = df.to_dict(orient="records")
            else:
                data = []

            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "data": [], "error": str(e)}


@router.get("/{material_id}")
def get_material(material_id: int):
    """Detalle de un material de maquila."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM materiales_maquila WHERE id = :id"),
            {"id": material_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Material no encontrado")
        d = dict(row._mapping)
        d["stock_actual"] = float(d.get("stock_actual") or 0)
        d["costo_unitario"] = float(d.get("costo_unitario") or 0)
        d["fecha_creacion"] = str(d.get("fecha_creacion"))
        d["fecha_actualizacion"] = str(d.get("fecha_actualizacion"))
        return {"ok": True, "data": d}


@router.post("")
def create_material(body: dict = Body(...), authorization: str = Header(None)):
    """Crea un nuevo material / insumo de maquila."""
    _require_admin(authorization)
    
    sku = str(body.get("sku") or "").strip().upper()
    nombre = str(body.get("nombre") or "").strip()
    descripcion = str(body.get("descripcion") or "").strip()
    categoria = str(body.get("categoria") or "INSUMO").strip().upper()
    unidad_medida = str(body.get("unidad_medida") or "UN").strip().upper()
    observaciones = str(body.get("observaciones") or "").strip()
    activo = bool(body.get("activo", True))
    
    try:
        stock_actual = float(body.get("stock_actual", 0) or 0)
    except Exception:
        stock_actual = 0.0

    try:
        costo_unitario = float(body.get("costo_unitario", 0) or 0)
        if costo_unitario < 0:
            costo_unitario = 0.0
    except Exception:
        costo_unitario = 0.0

    if not sku:
        raise HTTPException(status_code=400, detail="El código / SKU del material es obligatorio")
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre o descripción del material es obligatorio")

    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT id FROM materiales_maquila WHERE UPPER(sku) = :s"),
            {"s": sku}
        ).fetchone()
        if exists:
            raise HTTPException(status_code=400, detail=f"Ya existe un material registrado con el SKU '{sku}'")

        res = conn.execute(text("""
            INSERT INTO materiales_maquila (
                sku, nombre, descripcion, categoria, unidad_medida, stock_actual, costo_unitario, observaciones, activo
            ) VALUES (
                :sku, :nombre, :desc, :cat, :um, :stock, :costo, :obs, :act
            ) RETURNING id
        """), {
            "sku": sku,
            "nombre": nombre,
            "desc": descripcion,
            "cat": categoria,
            "um": unidad_medida,
            "stock": stock_actual,
            "costo": costo_unitario,
            "obs": observaciones,
            "act": activo
        })
        new_id = res.fetchone()[0]

    return {"ok": True, "id": new_id, "sku": sku, "msg": "Material creado exitosamente"}


@router.put("/{material_id}")
def update_material(material_id: int, body: dict = Body(...), authorization: str = Header(None)):
    """Actualiza datos de un material existente."""
    _require_admin(authorization)

    nombre = str(body.get("nombre") or "").strip()
    descripcion = str(body.get("descripcion") or "").strip()
    categoria = str(body.get("categoria") or "INSUMO").strip().upper()
    unidad_medida = str(body.get("unidad_medida") or "UN").strip().upper()
    observaciones = str(body.get("observaciones") or "").strip()
    activo = bool(body.get("activo", True))

    try:
        stock_actual = float(body.get("stock_actual", 0) or 0)
    except Exception:
        stock_actual = 0.0

    try:
        costo_unitario = float(body.get("costo_unitario", 0) or 0)
        if costo_unitario < 0:
            costo_unitario = 0.0
    except Exception:
        costo_unitario = 0.0

    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del material es obligatorio")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM materiales_maquila WHERE id = :id"),
            {"id": material_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Material no encontrado")

        conn.execute(text("""
            UPDATE materiales_maquila
            SET nombre = :nombre,
                descripcion = :desc,
                categoria = :cat,
                unidad_medida = :um,
                stock_actual = :stock,
                costo_unitario = :costo,
                observaciones = :obs,
                activo = :act,
                fecha_actualizacion = NOW()
            WHERE id = :id
        """), {
            "id": material_id,
            "nombre": nombre,
            "desc": descripcion,
            "cat": categoria,
            "um": unidad_medida,
            "stock": stock_actual,
            "costo": costo_unitario,
            "obs": observaciones,
            "act": activo
        })

    return {"ok": True, "msg": "Material actualizado correctamente"}


@router.delete("/{material_id}")
def delete_material(material_id: int, authorization: str = Header(None)):
    """Elimina un material del catálogo."""
    _require_admin(authorization)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT sku FROM materiales_maquila WHERE id = :id"),
            {"id": material_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Material no encontrado")
        
        sku = str(row[0])
        # Verificar si está en uso en alguna receta de maquila activa
        uso = conn.execute(text("""
            SELECT r.descripcion, r.sku_maquilable
            FROM receta_maquila_componentes c
            JOIN recetas_maquila r ON r.id = c.receta_id
            WHERE c.sku_componente = :sku
        """), {"sku": sku}).fetchall()

        if uso:
            recetas_nombres = ", ".join([str(u[0] or u[1]) for u in uso[:3]])
            raise HTTPException(
                status_code=400,
                detail=f"No se puede eliminar el material '{sku}' porque está siendo utilizado en las recetas: {recetas_nombres}. Desactiva o remueve el componente antes de eliminarlo."
            )

        conn.execute(text("DELETE FROM materiales_maquila WHERE id = :id"), {"id": material_id})

    return {"ok": True, "msg": f"Material '{sku}' eliminado correctamente"}


@router.post("/upload-inventario")
async def upload_inventario_materiales(file: UploadFile = File(...), authorization: str = Header(None)):
    """
    Sube un Excel de inventario de materiales con columnas 'sku', 'descripcion' y 'unidades'.
    Actualiza el stock y descripción de los materiales existentes y crea los que no existan.
    """
    _require_admin(authorization)

    fname = file.filename.lower()
    if not (fname.endswith(".xlsx") or fname.endswith(".xls") or fname.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Formato no compatible. Sube un archivo Excel (.xlsx, .xls) o .csv")

    try:
        contents = await file.read()
        if fname.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al leer el archivo Excel: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo subido está vacío")

    # Mapeo flexible de columnas para 'sku', 'descripcion', 'categoria', 'unidades' y 'costo'
    col_map = {}
    for c in df.columns:
        norm = str(c).strip().lower()
        if norm in ["sku", "codigo", "código", "item", "material", "cod_material"]:
            col_map["sku"] = c
        elif norm in ["descripcion", "descripción", "detalle", "nombre", "desc", "descripcion_material"]:
            col_map["descripcion"] = c
        elif norm in ["categoria", "categoría", "tipo", "rubro", "cat", "categoria_material"]:
            col_map["categoria"] = c
        elif norm in ["costo", "costo_unitario", "costo_u", "precio", "cost", "unit_cost", "costo_un"]:
            col_map["costo"] = c
        elif norm in ["unidades", "unidad", "stock", "cantidad", "cant", "stock_actual", "inventario", "uds"]:
            col_map["unidades"] = c

    if "sku" not in col_map:
        raise HTTPException(
            status_code=400,
            detail=f"Falta la columna obligatoria 'sku' en el archivo. Columnas detectadas: {list(df.columns)}"
        )
    if "unidades" not in col_map:
        raise HTTPException(
            status_code=400,
            detail=f"Falta la columna obligatoria 'unidades' en el archivo. Columnas detectadas: {list(df.columns)}"
        )

    sku_col = col_map["sku"]
    uds_col = col_map["unidades"]
    desc_col = col_map.get("descripcion")
    cat_col = col_map.get("categoria")
    cost_col = col_map.get("costo")

    actualizados = 0
    creados = 0
    errores = []

    with engine.begin() as conn:
        for idx, row in df.iterrows():
            row_num = idx + 2
            raw_sku = row.get(sku_col)
            if pd.isna(raw_sku) or str(raw_sku).strip() == "" or str(raw_sku).strip().lower() == "nan":
                continue

            sku = str(raw_sku).strip().upper()
            raw_uds = row.get(uds_col)
            raw_desc = row.get(desc_col) if desc_col else None
            desc = str(raw_desc).strip() if (raw_desc is not None and not pd.isna(raw_desc) and str(raw_desc).strip().lower() != "nan") else ""

            raw_cat = row.get(cat_col) if cat_col else None
            cat_raw = str(raw_cat).strip().upper() if (raw_cat is not None and not pd.isna(raw_cat) and str(raw_cat).strip().lower() != "nan") else ""
            if "ETIQ" in cat_raw:
                cat = "ETIQUETA"
            elif "MANGA" in cat_raw or "CELOF" in cat_raw:
                cat = "MANGA"
            elif "EMP" in cat_raw or "CAJA" in cat_raw or "BOLSA" in cat_raw:
                cat = "EMPAQUE"
            elif cat_raw in ["INSUMO", "OTRO"]:
                cat = cat_raw
            elif cat_raw:
                cat = cat_raw
            else:
                cat = "INSUMO"

            raw_cost = row.get(cost_col) if cost_col else None
            try:
                cost_val = float(raw_cost) if (raw_cost is not None and not pd.isna(raw_cost)) else None
                if cost_val is not None and cost_val < 0:
                    cost_val = 0.0
            except Exception:
                cost_val = None

            try:
                if pd.isna(raw_uds):
                    uds = 0.0
                else:
                    uds = float(raw_uds)
                if uds < 0:
                    uds = 0.0
            except Exception:
                errores.append(f"Fila {row_num}: cantidad inválida '{raw_uds}' para SKU '{sku}'")
                continue

            # Verificar si existe
            existing = conn.execute(
                text("SELECT id FROM materiales_maquila WHERE UPPER(sku) = :s"),
                {"s": sku}
            ).fetchone()

            if existing:
                set_clauses = ["stock_actual = :stock", "fecha_actualizacion = NOW()"]
                params = {"stock": uds, "id": existing[0]}
                if desc:
                    set_clauses.extend(["nombre = :desc", "descripcion = :desc"])
                    params["desc"] = desc
                if cat_raw:
                    set_clauses.append("categoria = :cat")
                    params["cat"] = cat
                if cost_val is not None:
                    set_clauses.append("costo_unitario = :costo")
                    params["costo"] = cost_val

                conn.execute(text(f"""
                    UPDATE materiales_maquila
                    SET {", ".join(set_clauses)}
                    WHERE id = :id
                """), params)
                actualizados += 1
            else:
                # Crear nuevo material con ese stock, descripción, categoría y costo
                nombre_defecto = desc if desc else f"Material {sku}"
                conn.execute(text("""
                    INSERT INTO materiales_maquila (
                        sku, nombre, descripcion, unidad_medida, stock_actual, costo_unitario, categoria, observaciones
                    ) VALUES (
                        :sku, :nombre, :desc, 'UN', :stock, :costo, :cat, 'Creado vía carga masiva de inventario'
                    )
                """), {
                    "sku": sku,
                    "nombre": nombre_defecto,
                    "desc": desc,
                    "stock": uds,
                    "costo": (cost_val or 0.0),
                    "cat": cat
                })
                creados += 1

    return {
        "ok": True,
        "mensaje": f"Carga procesada: {actualizados} materiales actualizados y {creados} nuevos creados.",
        "total_procesados": actualizados + creados,
        "actualizados": actualizados,
        "creados": creados,
        "errores": errores
    }


@router.get("/plantilla-excel")
def download_plantilla_excel():
    """Descarga la plantilla Excel con las cinco columnas: sku, descripcion, categoria, unidades y costo."""
    df_sample = pd.DataFrame([
        {"sku": "ETIQ-50X30", "descripcion": "Etiqueta adhesiva 50x30 mm", "categoria": "ETIQUETA", "unidades": 1500, "costo": 15.50},
        {"sku": "MANGA-CEL-20CM", "descripcion": "Manga de celofán transparente 20 cm", "categoria": "MANGA", "unidades": 3200, "costo": 25.00},
        {"sku": "BOLSA-POLI-10X15", "descripcion": "Bolsa polietileno 10x15 cm con cierre", "categoria": "EMPAQUE", "unidades": 850, "costo": 12.00},
        {"sku": "CAJA-MAESTRA-100U", "descripcion": "Caja de cartón master para 100 unidades", "categoria": "EMPAQUE", "unidades": 45, "costo": 180.00}
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_sample.to_excel(writer, sheet_name="Inventario_Materiales", index=False)
    output.seek(0)

    filename = "Plantilla_Inventario_Materiales_Maquila.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/export-excel")
def export_materiales_excel():
    """Exporta el catálogo completo de materiales de maquila con su stock a Excel."""
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT 
                sku AS "SKU / Código",
                nombre AS "Nombre del Material",
                categoria AS "Categoría",
                unidad_medida AS "Unidad de Medida",
                stock_actual AS "Stock Actual (Unidades)",
                COALESCE(costo_unitario, 0) AS "Costo Unitario ($)",
                ROUND(CAST(stock_actual * COALESCE(costo_unitario, 0) AS numeric), 2) AS "Valor Total ($)",
                observaciones AS "Observaciones",
                CASE WHEN activo THEN 'ACTIVO' ELSE 'INACTIVO' END AS "Estado",
                TO_CHAR(fecha_actualizacion, 'YYYY-MM-DD HH24:MI') AS "Última Actualización"
            FROM materiales_maquila
            ORDER BY sku ASC
        """), conn)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Materiales_Maquila", index=False)
        output.seek(0)

        filename = f"Materiales_Maquila_Inventario_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
