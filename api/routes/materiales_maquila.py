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
                sku, nombre, descripcion, categoria, unidad_medida, stock_actual, observaciones, activo
            ) VALUES (
                :sku, :nombre, :desc, :cat, :um, :stock, :obs, :act
            ) RETURNING id
        """), {
            "sku": sku,
            "nombre": nombre,
            "desc": descripcion,
            "cat": categoria,
            "um": unidad_medida,
            "stock": stock_actual,
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
    Sube un Excel simple de inventario de materiales con columnas 'sku' y 'unidades'.
    Actualiza el stock de los materiales existentes y crea los que no existan.
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

    # Mapeo flexible de columnas para 'sku' y 'unidades'
    col_map = {}
    for c in df.columns:
        norm = str(c).strip().lower()
        if norm in ["sku", "codigo", "código", "item", "material", "cod_material"]:
            col_map["sku"] = c
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
                conn.execute(text("""
                    UPDATE materiales_maquila
                    SET stock_actual = :stock, fecha_actualizacion = NOW()
                    WHERE id = :id
                """), {"stock": uds, "id": existing[0]})
                actualizados += 1
            else:
                # Crear nuevo material con ese stock
                nombre_defecto = f"Material {sku}"
                conn.execute(text("""
                    INSERT INTO materiales_maquila (
                        sku, nombre, unidad_medida, stock_actual, categoria, observaciones
                    ) VALUES (
                        :sku, :nombre, 'UN', :stock, 'INSUMO', 'Creado vía carga masiva de inventario'
                    )
                """), {"sku": sku, "nombre": nombre_defecto, "stock": uds})
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
    """Descarga la plantilla Excel con las dos columnas requeridas: sku y unidades."""
    df_sample = pd.DataFrame([
        {"sku": "ETIQ-50X30", "unidades": 1500},
        {"sku": "MANGA-CEL-20CM", "unidades": 3200},
        {"sku": "BOLSA-POLI-10X15", "unidades": 850},
        {"sku": "CAJA-MAESTRA-100U", "unidades": 45}
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_sample.to_excel(writer, sheet_name="Inventario_Materiales", index=False)
    output.seek(0)

    filename = "Plantilla_Inventario_Materiales_Maquila.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
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
