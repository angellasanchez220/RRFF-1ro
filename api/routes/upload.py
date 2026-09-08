"""
api/routes/upload.py — Endpoints de carga de archivos y gestión de OCs
=======================================================================
- POST /api/upload/maestro        → reemplaza dim_productos (col T = ump)
- POST /api/upload/inventario     → reemplaza stock en dim_productos (truncate+insert)
- POST /api/upload/transito       → agrega OCs al control_embarques
- GET  /api/upload/embarques      → lista todas las OCs
- POST /api/upload/embarques/{id}/aforo   → marcar en aforo (+7d, luego +14d total)
- POST /api/upload/embarques/{id}/eta     → cambiar ETA (atraso)
- POST /api/upload/embarques/{id}/llegada → confirmar llegada (sale del tránsito)
- POST /api/upload/reprocess      → reprocesar pipeline completo
"""
import io
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy import text

ROOT      = Path(__file__).resolve().parent.parent.parent
RAW_DIR   = ROOT / "data" / "raw"
MANUAL_DIR = ROOT / "data" / "manual_uploads"
OC_DIR    = ROOT / "data" / "manual_uploads" / "ordenes_compra"

router = APIRouter()

# ── Auth helpers (importados de auth.py) ──────────────────────────────────────
from api.routes.auth import decode_token, _get_auth_header, require_admin, require_permission

# ── Columnas Maestra ──────────────────────────────────────────────────────────
# Fila 2 como header, columnas (0-based): B=1, C=2, E=4, F=5, G=6, M=12, T=19
MAESTRO_COL_IDX = [1, 2, 4, 5, 6, 12, 19]
MAESTRO_COL_NAMES = ["codigo_femaco", "sku", "categoria", "subcategoria", "formato", "condicion", "ump"]


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD MAESTRA
# ─────────────────────────────────────────────────────────────────────────────

def _run_planner_task():
    try:
        subprocess.run([sys.executable, str(ROOT / "src" / "planner.py")], check=True, timeout=120)
    except Exception as e:
        print(f"Error lanzando planner.py en segundo plano: {e}")

@router.post("/maestro")
async def upload_maestro(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    authorization: str = Header(None),
):
    """Sube la Maestra. UPSERT por SKU. Columna T = ump (U/E = unidades/caja)."""
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_upload_maestro"):
        raise HTTPException(403, "Sin permiso para subir Maestra")

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Solo se aceptan archivos Excel (.xlsx, .xls)")

    contents = await file.read()
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (MANUAL_DIR / file.filename).write_bytes(contents)
    except PermissionError:
        raise HTTPException(400, "El archivo está bloqueado. Ciérralo en Excel antes de subirlo.")
    except Exception as e:
        raise HTTPException(500, f"Error al guardar el archivo: {e}")

    try:
        df = pd.read_excel(io.BytesIO(contents), header=1, dtype=str)
    except Exception as e:
        raise HTTPException(400, f"Error al leer el Excel: {e}")

    n_cols = len(df.columns)

    # Columnas requeridas (0-based): B=1, C=2, E=4, F=5, G=6, M=12
    REQUIRED_IDX = [1, 2, 4, 5, 6, 12]
    if n_cols < 13:
        raise HTTPException(400, f"El archivo tiene solo {n_cols} columnas. Se necesitan al menos 13 (hasta M).")

    try:
        sub = df.iloc[:, REQUIRED_IDX].copy()
    except Exception as e:
        raise HTTPException(400, f"Error al extraer columnas: {e}")

    sub.columns = ["codigo_femaco", "sku", "categoria", "subcategoria", "formato", "condicion"]

    # Columna T (índice 19) = ump — opcional
    if n_cols > 19:
        try:
            sub["ump"] = pd.to_numeric(
                df.iloc[:, 19].astype(str).str.replace(",", "."), errors="coerce"
            )
        except Exception:
            sub["ump"] = None
    else:
        sub["ump"] = None

    sub = sub.fillna("")
    sub["sku"]          = sub["sku"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    sub["codigo_femaco"] = sub["codigo_femaco"].astype(str).str.strip()
    sub["condicion"]    = sub["condicion"].astype(str).str.strip()
    sub["es_nuevo"]     = sub["sku"].apply(lambda x: x in ("", "nan", "None"))
    sub = sub[sub["codigo_femaco"].notna() & (sub["codigo_femaco"] != "") & (sub["codigo_femaco"] != "nan")]
    sub = sub.reset_index(drop=True)

    from api.db import engine
    updated = inserted = 0
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dim_productos (
                    sku TEXT PRIMARY KEY,
                    codigo_femaco TEXT,
                    stock_act FLOAT DEFAULT 0,
                    nombre_producto TEXT,
                    categoria TEXT,
                    subcategoria TEXT,
                    formato TEXT,
                    estado TEXT,
                    departamento TEXT,
                    familia TEXT,
                    subfamilia TEXT,
                    grupo TEXT,
                    conjunto TEXT,
                    gancheras FLOAT,
                    condicion TEXT,
                    ump FLOAT
                )
            """))
            conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS condicion TEXT"))
            conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS ump FLOAT"))

            for _, row in sub.iterrows():
                sku_val = row["sku"] if not row["es_nuevo"] else None
                ump_val = float(row["ump"]) if pd.notna(row.get("ump")) and row.get("ump") != "" else None

                if sku_val:
                    r = conn.execute(text("SELECT 1 FROM dim_productos WHERE sku=:s"), {"s": sku_val})
                    if r.fetchone():
                        conn.execute(text("""
                            UPDATE dim_productos
                            SET codigo_femaco=:cf, categoria=:cat, subcategoria=:sub,
                                formato=:fmt, condicion=:cond, ump=COALESCE(:ump, ump)
                            WHERE sku=:sku
                        """), {
                            "cf": row["codigo_femaco"], "cat": row["categoria"],
                            "sub": row["subcategoria"], "fmt": row["formato"],
                            "cond": row["condicion"], "ump": ump_val, "sku": sku_val
                        })
                        updated += 1
                        continue

                if row["codigo_femaco"]:
                    conn.execute(text("""
                        INSERT INTO dim_productos
                            (sku, codigo_femaco, nombre_producto, categoria,
                             subcategoria, formato, condicion, ump)
                        VALUES (:sku, :cf, 'PRODUCTO NUEVO', :cat, :sub, :fmt, :cond, :ump)
                        ON CONFLICT (sku) DO UPDATE SET
                            codigo_femaco=EXCLUDED.codigo_femaco,
                            categoria=EXCLUDED.categoria,
                            subcategoria=EXCLUDED.subcategoria,
                            formato=EXCLUDED.formato,
                            condicion=EXCLUDED.condicion,
                            ump=COALESCE(EXCLUDED.ump, dim_productos.ump)
                    """), {
                        "sku": sku_val or row["codigo_femaco"],
                        "cf": row["codigo_femaco"], "cat": row["categoria"],
                        "sub": row["subcategoria"], "fmt": row["formato"],
                        "cond": row["condicion"], "ump": ump_val,
                    })
                    inserted += 1

    except Exception as db_err:
        raise HTTPException(500, f"Error en la base de datos: {db_err}")

    # Lanzar recálculo de planificación de forma asincrónica (sin bloquear la petición HTTP)
    background_tasks.add_task(_run_planner_task)

    preview = sub.head(20).replace({float("nan"): None}).to_dict(orient="records")
    return {
        "ok": True, "actualizados": updated, "insertados": inserted,
        "total_filas": len(sub), "preview": preview,
    }



# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD INVENTARIO — reemplazo total de stock
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/inventario")
async def upload_inventario(
    file: UploadFile = File(...),
    authorization: str = Header(None),
):
    """Sube el inventario semanal. Reemplaza stock_act en dim_productos."""
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_upload_inventario"):
        raise HTTPException(403, "Sin permiso para subir Inventario")

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Solo se aceptan archivos Excel (.xlsx, .xls)")

    contents = await file.read()
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (MANUAL_DIR / file.filename).write_bytes(contents)
    except PermissionError:
        raise HTTPException(400, "El archivo esta bloqueado. Cierralo en Excel antes de subirlo.")
    except Exception as e:
        raise HTTPException(500, f"Error al guardar el archivo: {e}")

    # Intentar leer con hoja "INVENTARIO FINAL" (que es realmente la que contiene STOCK ACT en la columna E)
    df = None
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
        # Buscar hoja que contenga "INVENTARIO FINAL"
        target_sheet = next((s for s in xl.sheet_names if "INVENTARIO FINAL" in s.upper()), None)
        
        if target_sheet:
            # En INVENTARIO FINAL:
            # Columna A (0): COD_CAJA
            # Columna B (1): SKU
            # Columna E (4): STOCK ACT
            # La cabecera esta en la fila 0
            df = xl.parse(sheet_name=target_sheet, header=0)
        else:
            # Fallback a lectura genérica si no existe esa hoja
            for sheet, hdr in [(0, 0), (1, 0), (1, 1), (3, 0)]:
                try:
                    df = pd.read_excel(io.BytesIO(contents), sheet_name=sheet, header=hdr)
                    if len(df.columns) >= 5:
                        break
                except Exception:
                    continue
    except Exception as e:
        raise HTTPException(400, f"Error leyendo Excel: {e}")

    if df is None or len(df.columns) < 5:
        raise HTTPException(400, "No se pudo leer el archivo de inventario o no tiene al menos 5 columnas (hasta la E).")

    # Extraer columnas según reglas del usuario (A=0, B=1, E=4)
    try:
        col_caja = df.iloc[:, 0]
        col_sku = df.iloc[:, 1]
        col_stock = df.iloc[:, 4]
        
        # Consolidar SKU: Si B está vacío/nulo, usar A
        sku_final = col_sku.copy()
        mask_empty = sku_final.isna() | (sku_final.astype(str).str.strip() == "") | (sku_final.astype(str).str.strip().str.lower() == "nan") | (sku_final.astype(str).str.strip() == "0")
        sku_final.loc[mask_empty] = col_caja.loc[mask_empty]
        
        sub = pd.DataFrame({"sku": sku_final, "stock_act": col_stock})
    except Exception as e:
        raise HTTPException(400, f"Error extrayendo columnas A, B, E: {e}")

    sub["sku"]       = sub["sku"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    sub["stock_act"] = pd.to_numeric(sub["stock_act"], errors="coerce").fillna(0)
    sub = sub[sub["sku"].notna() & (sub["sku"] != "") & (sub["sku"] != "nan") & (sub["sku"] != "None") & (sub["sku"] != "0")]

    if sub.empty:
        raise HTTPException(400, "No se encontraron filas validas con SKU (Revisando columnas A y B).")

    from api.db import engine
    updated = 0
    no_match = []
    try:
        with engine.begin() as conn:
            # Asegurar columna stock_act existe
            conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS stock_act FLOAT DEFAULT 0"))
            # Limpiar NULLs previos
            conn.execute(text("UPDATE dim_productos SET stock_act = 0 WHERE stock_act IS NULL"))
            # Resetear todo a 0 (reemplazo total del inventario)
            conn.execute(text("UPDATE dim_productos SET stock_act = 0"))
            # Actualizar con los valores del archivo
            for _, row in sub.iterrows():
                r = conn.execute(
                    text("UPDATE dim_productos SET stock_act=:s WHERE sku=:u RETURNING sku"),
                    {"s": float(row["stock_act"]), "u": row["sku"]}
                )
                if r.fetchone():
                    updated += 1
                else:
                    no_match.append(row["sku"])
    except Exception as db_err:
        raise HTTPException(500, f"Error actualizando el inventario: {db_err}")

    # Ejecutar planner.py de forma sincrónica para que los datos estén listos en el dashboard
    try:
        subprocess.run([sys.executable, str(ROOT / "src" / "planner.py")], check=True, capture_output=True)
    except Exception as e:
        print(f"Error lanzando planner.py: {e}")

    preview = sub.head(20).to_dict(orient="records")
    return {
        "ok": True,
        "actualizados": updated,
        "total_filas": len(sub),
        "sin_match": len(no_match),
        "sin_match_skus": no_match[:10],
        "preview": preview,
        "aviso": (
            f"ATENCION: {len(no_match)} SKUs del archivo no existen en la Maestra. "
            "Sube primero la Maestra y luego el Inventario."
        ) if no_match else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD TRÁNSITO / OC → control_embarques
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/transito")
async def upload_transito(
    file: UploadFile = File(...),
    nombre_pedido: str = Form(default=""),
    eta_fecha:     str = Form(default=""),
    authorization: str = Header(None),
):
    """
    Sube una OC Excel. Detecta columnas CODIGO_FEMACO + CANTIDAD_OC + ETA.
    Acepta nombre_pedido y eta_fecha como campos del formulario (obligatorio nombre_pedido).
    Inserta en control_embarques (acumulativo — las anteriores se mantienen).
    """
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_upload_transito"):
        raise HTTPException(403, "Sin permiso para subir OC")

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Solo se aceptan archivos Excel (.xlsx, .xls)")

    contents = await file.read()
    OC_DIR.mkdir(parents=True, exist_ok=True)
    dest = OC_DIR / file.filename
    try:
        dest.write_bytes(contents)
    except PermissionError:
        raise HTTPException(400, "El archivo de la OC está bloqueado. Ciérralo en Excel antes de subirlo.")
    except Exception as e:
        raise HTTPException(500, f"Error al guardar la OC: {e}")

    # ── Leer Excel (Primeras 2 columnas) ──────────────────────────────────────
    try:
        # Se asume fila 0 como header. Si el usuario envía la info desde la fila 1,
        # pandas lo leerá bien. Tomamos las columnas 0 y 1.
        df = pd.read_excel(io.BytesIO(contents), sheet_name=0)
    except Exception as e:
        raise HTTPException(400, f"Error al leer el Excel de OC: {e}")

    if len(df.columns) < 2:
        raise HTTPException(400, "El archivo debe tener al menos 2 columnas (Código y Cantidad).")

    df = df.iloc[:, [0, 1]].copy()
    df.columns = ["uploaded_code", "cantidad"]

    df["uploaded_code"] = df["uploaded_code"].astype(str).str.strip()
    df["cantidad"]      = pd.to_numeric(df["cantidad"], errors="coerce")
    df = df.dropna(subset=["uploaded_code", "cantidad"])
    df = df[df["cantidad"] > 0]

    # Agrupar repeticiones del mismo producto en la misma OC
    df = df.groupby("uploaded_code", as_index=False).agg({"cantidad": "sum"})

    if df.empty:
        raise HTTPException(400, "No se encontraron filas válidas con cantidad > 0")

    # Cruzar con dim_productos para obtener SKU y Nombre permitiendo SKU o Código Femaco
    from api.db import engine
    dim = pd.read_sql("SELECT sku, codigo_femaco, nombre_producto FROM dim_productos", engine)
    
    mapping = {}
    for _, row in dim.iterrows():
        s = str(row["sku"]).strip()
        c = str(row["codigo_femaco"]).strip()
        data = {"sku": s, "codigo_femaco": c, "nombre_producto": row["nombre_producto"]}
        if s and s != "None" and s != "nan":
            mapping[s] = data
        if c and c != "None" and c != "nan":
            mapping[c] = data

    def map_row(code):
        return mapping.get(code, {"sku": None, "codigo_femaco": code, "nombre_producto": None})

    mapped = df["uploaded_code"].apply(map_row)
    df["sku"] = [x["sku"] for x in mapped]
    df["codigo_femaco"] = [x["codigo_femaco"] for x in mapped]
    df["nombre_producto"] = [x["nombre_producto"] for x in mapped]

    # Parsear ETA: priorizar eta_fecha del formulario sobre la del Excel
    def _parse_eta(v):
        try:
            return pd.Timestamp(str(v)).date() if pd.notna(v) else None
        except Exception:
            return None

    # ETA del formulario tiene prioridad
    eta_form = _parse_eta(eta_fecha) if eta_fecha else None

    if "fecha_eta_raw" in df.columns:
        df["fecha_eta"] = df["fecha_eta_raw"].apply(_parse_eta)
    else:
        df["fecha_eta"] = None

    # Si viene eta del form, aplicarla a todas las filas
    if eta_form:
        df["fecha_eta"] = eta_form

    df["fecha_disponibilidad_real"] = df["fecha_eta"].apply(
        lambda e: (e + timedelta(days=7)) if e else None
    )

    # Asegurar columna nombre_pedido en la tabla
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE control_embarques ADD COLUMN IF NOT EXISTS nombre_pedido TEXT"
        ))

    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            # codigo_envio y nombre_pedido SIEMPRE vienen del formulario (nombre_pedido)
            oc_ref = nombre_pedido.strip() if nombre_pedido else file.filename
            sku_val = str(row.get("sku", "")) if pd.notna(row.get("sku")) else None
            nom_val = str(row.get("nombre_producto", "")) if pd.notna(row.get("nombre_producto")) else ""
            conn.execute(text("""
                INSERT INTO control_embarques
                    (codigo_envio, nombre_pedido, sku, codigo_femaco, nombre_producto,
                     cantidad, fecha_eta, fecha_disponibilidad_real,
                     origen_eta, nombre_archivo, estado)
                VALUES
                    (:oc, :pedido, :sku, :cf, :nom, :qty, :eta, :disp,
                     'excel_oc', :arch, 'EN_TRANSITO')
            """), {
                "oc":    oc_ref,
                "pedido": oc_ref,
                "sku":   sku_val if sku_val and sku_val not in ("", "None", "nan") else None,
                "cf":    row["codigo_femaco"],
                "nom":   nom_val,
                "qty":   int(row["cantidad"]),
                "eta":   row["fecha_eta"],
                "disp":  row["fecha_disponibilidad_real"],
                "arch":  file.filename,
            })
            inserted += 1

    return {"ok": True, "insertadas": inserted, "archivo": file.filename,
            "nombre_pedido": oc_ref, "sin_sku": int(df["sku"].isna().sum())}


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE EMBARQUES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/embarques")
def get_embarques(authorization: str = Header(None)):
    """Lista todas las OCs almacenadas en control_embarques."""
    token = _get_auth_header(authorization)
    decode_token(token)  # solo verifica autenticación

    from api.db import engine
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT id, codigo_envio, sku, codigo_femaco, nombre_producto,
                   cantidad, fecha_eta, fecha_disponibilidad_real,
                   COALESCE(eta_ajustada, fecha_disponibilidad_real) AS eta_efectiva,
                   origen_eta, nombre_archivo, estado,
                   en_aforo, fecha_marcado_aforo, eta_ajustada,
                   fecha_llegada_real, observacion, creado_en
            FROM control_embarques
            ORDER BY
                CASE estado
                    WHEN 'EN_TRANSITO' THEN 1
                    WHEN 'EN_AFORO'    THEN 2
                    WHEN 'RETRASADO'   THEN 3
                    WHEN 'LLEGADO'     THEN 4
                    ELSE 5
                END,
                fecha_eta NULLS LAST
        """), conn)

    records = []
    for _, row in df.iterrows():
        r = {}
        for c in df.columns:
            v = row[c]
            if pd.isna(v) if not isinstance(v, (str, bool)) else (v is None):
                r[c] = None
            elif hasattr(v, "isoformat"):
                r[c] = str(v)[:10]
            elif hasattr(v, "item"):
                r[c] = v.item()
            else:
                r[c] = v
        records.append(r)
    return {"embarques": records, "total": len(records)}


@router.post("/embarques/{emb_id}/aforo")
def marcar_aforo(emb_id: int, authorization: str = Header(None)):
    """
    Marca una OC en aforo.
    - 1ª vez: ETA_disponible = fecha_ETA_original + 7 días
    - Si ya pasó la semana de aforo y no llegó: ETA_disponible = fecha_ETA_original + 14 días
      (y se alerta para contactar al proveedor si tampoco llega)
    """
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    from api.db import engine
    today = date.today()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM control_embarques WHERE id=:i"), {"i": emb_id}
        ).fetchone()

    if not row:
        raise HTTPException(404, "OC no encontrada")

    eta_orig = row.fecha_eta
    ya_en_aforo = row.en_aforo
    fecha_aforo = row.fecha_marcado_aforo

    if not ya_en_aforo:
        # Primera vez: +7 días
        nueva_disp = (eta_orig + timedelta(days=7)) if eta_orig else (today + timedelta(days=7))
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE control_embarques
                SET en_aforo=TRUE, estado='EN_AFORO',
                    fecha_marcado_aforo=:hoy,
                    fecha_disponibilidad_real=:disp,
                    actualizado_en=NOW()
                WHERE id=:i
            """), {"hoy": today, "disp": nueva_disp, "i": emb_id})
        return {"ok": True, "msg": "Aforo marcado (+7 días). Disponible: " + str(nueva_disp), "alerta": False}

    else:
        # Segunda vez: +14 días total → alerta proveedor
        nueva_disp = (eta_orig + timedelta(days=14)) if eta_orig else (today + timedelta(days=7))
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE control_embarques
                SET estado='EN_AFORO',
                    fecha_disponibilidad_real=:disp,
                    actualizado_en=NOW()
                WHERE id=:i
            """), {"disp": nueva_disp, "i": emb_id})
        return {
            "ok": True,
            "msg": f"Aforo extendido (+14 días total). Disponible: {nueva_disp}",
            "alerta": True,
            "alerta_msg": "⚠️ Han pasado más de 14 días desde el ETA original. Contactar al vendedor.",
        }


@router.post("/embarques/{emb_id}/eta")
def cambiar_eta(emb_id: int, body: dict = Body(...), authorization: str = Header(None)):
    """
    Cambia la ETA por atraso. La OC sigue en tránsito (RETRASADO).
    body: { "nueva_eta": "2026-06-15", "motivo": "texto opcional" }
    """
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    nueva_eta_str = body.get("nueva_eta")
    if not nueva_eta_str:
        raise HTTPException(400, "Se requiere nueva_eta (YYYY-MM-DD)")

    try:
        nueva_eta = date.fromisoformat(str(nueva_eta_str)[:10])
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido. Use YYYY-MM-DD")

    # Buffer aforo desde nueva ETA
    nueva_disp = nueva_eta + timedelta(days=7)
    motivo = body.get("motivo", "")

    from api.db import engine
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE control_embarques
            SET eta_ajustada=:eta, fecha_disponibilidad_real=:disp,
                estado='RETRASADO', observacion=CONCAT(COALESCE(observacion,''), :mot),
                actualizado_en=NOW()
            WHERE id=:i
        """), {
            "eta":  nueva_eta,
            "disp": nueva_disp,
            "mot":  f"\n[ATRASO] Nueva ETA: {nueva_eta}. {motivo}".strip(),
            "i":    emb_id
        })
    return {"ok": True, "nueva_eta": str(nueva_eta), "disponible": str(nueva_disp)}


@router.post("/embarques/{emb_id}/llegada")
def confirmar_llegada(emb_id: int, body: dict = Body(default={}), authorization: str = Header(None)):
    """
    Confirma que la OC llegó. Estado → LLEGADO. Sale del tránsito activo.
    body: { "fecha_llegada": "2026-06-10" }  (opcional, default = hoy)
    """
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    fecha_str = body.get("fecha_llegada")
    if fecha_str:
        try:
            fecha = date.fromisoformat(str(fecha_str)[:10])
        except ValueError:
            fecha = date.today()
    else:
        fecha = date.today()

    from api.db import engine
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE control_embarques
            SET estado='LLEGADO', fecha_llegada_real=:f,
                actualizado_en=NOW()
            WHERE id=:i
        """), {"f": fecha, "i": emb_id})
    return {"ok": True, "fecha_llegada": str(fecha)}

@router.post("/embarques/oc/{nombre_pedido:path}/aforo")
def marcar_aforo_oc(nombre_pedido: str, authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    from api.db import engine
    today = date.today()
    updated = 0
    with engine.begin() as conn:
        items = conn.execute(
            text("SELECT id, fecha_eta, en_aforo FROM control_embarques WHERE nombre_pedido=:np AND estado != 'LLEGADO'"),
            {"np": nombre_pedido}
        ).fetchall()
        
        if not items:
            raise HTTPException(404, "OC no encontrada o todos sus ítems ya llegaron")

        for row in items:
            eta_orig = row.fecha_eta
            ya_en_aforo = row.en_aforo
            if not ya_en_aforo:
                nueva_disp = (eta_orig + timedelta(days=7)) if eta_orig else (today + timedelta(days=7))
                conn.execute(text("""
                    UPDATE control_embarques
                    SET en_aforo=TRUE, estado='EN_AFORO',
                        fecha_marcado_aforo=:hoy,
                        fecha_disponibilidad_real=:disp,
                        actualizado_en=NOW()
                    WHERE id=:i
                """), {"hoy": today, "disp": nueva_disp, "i": row.id})
            else:
                nueva_disp = (eta_orig + timedelta(days=14)) if eta_orig else (today + timedelta(days=7))
                conn.execute(text("""
                    UPDATE control_embarques
                    SET estado='EN_AFORO',
                        fecha_disponibilidad_real=:disp,
                        actualizado_en=NOW()
                    WHERE id=:i
                """), {"disp": nueva_disp, "i": row.id})
            updated += 1

    return {"ok": True, "msg": f"Aforo marcado para {updated} ítems de la OC {nombre_pedido}", "alerta": False}

@router.post("/embarques/oc/{nombre_pedido:path}/eta")
def cambiar_eta_oc(nombre_pedido: str, body: dict = Body(...), authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    nueva_eta_str = body.get("nueva_eta")
    if not nueva_eta_str:
        raise HTTPException(400, "Se requiere nueva_eta")

    try:
        nueva_eta = date.fromisoformat(str(nueva_eta_str)[:10])
    except ValueError:
        raise HTTPException(400, "Formato inválido. Use YYYY-MM-DD")

    nueva_disp = nueva_eta + timedelta(days=7)
    motivo = body.get("motivo", "")
    
    from api.db import engine
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE control_embarques
            SET eta_ajustada=:eta, fecha_disponibilidad_real=:disp,
                estado='RETRASADO', observacion=CONCAT(COALESCE(observacion,''), :mot),
                actualizado_en=NOW()
            WHERE nombre_pedido=:np AND estado != 'LLEGADO'
            RETURNING id
        """), {
            "eta": nueva_eta,
            "disp": nueva_disp,
            "mot": f"\n[ATRASO OC] Nueva ETA: {nueva_eta}. {motivo}".strip(),
            "np": nombre_pedido
        }).fetchall()
        
    if not res:
        raise HTTPException(404, "OC no encontrada o ya llegó completamente")

    return {"ok": True, "msg": f"ETA actualizada para {len(res)} ítems de la OC {nombre_pedido}"}

@router.post("/embarques/oc/{nombre_pedido:path}/llegada")
def confirmar_llegada_oc(nombre_pedido: str, body: dict = Body(default={}), authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    fecha_str = body.get("fecha_llegada")
    if fecha_str:
        try:
            fecha = date.fromisoformat(str(fecha_str)[:10])
        except ValueError:
            fecha = date.today()
    else:
        fecha = date.today()

    from api.db import engine
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE control_embarques
            SET estado='LLEGADO', fecha_llegada_real=:f,
                actualizado_en=NOW()
            WHERE nombre_pedido=:np AND estado != 'LLEGADO'
            RETURNING id
        """), {"f": fecha, "np": nombre_pedido}).fetchall()
        
    if not res:
        raise HTTPException(404, "OC no encontrada o ya llegó completamente")

    return {"ok": True, "msg": f"Llegada confirmada para {len(res)} ítems de la OC {nombre_pedido}"}

@router.delete("/embarques/oc/{nombre_pedido:path}")
def delete_embarque_oc(nombre_pedido: str, authorization: str = Header(None)):
    """Borra todos los embarques asociados a una OC / nombre_pedido."""
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    if payload.get("role") != "admin" and not permisos.get("can_manage_oc"):
        raise HTTPException(403, "Sin permiso para gestionar OCs")

    from api.db import engine
    with engine.begin() as conn:
        res = conn.execute(
            text("DELETE FROM control_embarques WHERE nombre_pedido = :np RETURNING id"),
            {"np": nombre_pedido}
        ).fetchall()
        
    if not res:
        raise HTTPException(404, "OC no encontrada o ya fue borrada")

    return {"ok": True, "msg": f"OC {nombre_pedido} borrada ({len(res)} SKUs eliminados)."}


# ─────────────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, UploadFile, BackgroundTasks

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN FEMACO SHINYAPPS (BACKGROUND TASK)
# ─────────────────────────────────────────────────────────────────────────────

import json
from datetime import datetime

TASK_STATUS_FILE = ROOT / "data" / "task_status.json"

def set_task_status(task_name, status, msg=""):
    try:
        TASK_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if TASK_STATUS_FILE.exists():
            data = json.loads(TASK_STATUS_FILE.read_text())
        data[task_name] = {
            "status": status,
            "msg": msg,
            "updated_at": datetime.now().isoformat()
        }
        TASK_STATUS_FILE.write_text(json.dumps(data))
    except Exception as e:
        print(f"Error guardando estado de tarea: {e}")

def _run_extract_task():
    """Tarea larga en segundo plano para evitar timeout de 100s de Render."""
    set_task_status("extract", "running", "Extrayendo datos de Matrix...")
    try:
        subprocess.run([sys.executable, "src/extractor.py"], cwd=str(ROOT), check=True, timeout=300)
        set_task_status("extract", "running", "Transformando datos...")
        subprocess.run([sys.executable, "src/transformer.py"], cwd=str(ROOT), check=True, timeout=120)
        set_task_status("extract", "running", "Cargando en BD...")
        subprocess.run([sys.executable, "src/loader.py"], cwd=str(ROOT), check=True, timeout=120)
        set_task_status("extract", "running", "Calculando S&OP...")
        subprocess.run([sys.executable, "src/planner.py"], cwd=str(ROOT), check=True, timeout=120)
        set_task_status("extract", "done", "Sincronización de Matrix completada con éxito.")
    except subprocess.CalledProcessError as e:
        msg = f"Error crítico en pipeline (fail-fast) - Etapa fallida: {e.cmd}"
        print(msg)
        set_task_status("extract", "error", msg)
    except Exception as e:
        msg = f"Error en tarea de extracción: {e}"
        print(msg)
        set_task_status("extract", "error", msg)

@router.post("/extract")
async def run_extract(background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """Inicia la extracción en segundo plano y responde inmediatamente."""
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(403, "Solo el admin puede extraer datos")

    background_tasks.add_task(_run_extract_task)
    return {
        "ok": True,
        "msg": "El robot de extracción ha iniciado en segundo plano. Los datos se actualizarán en un par de minutos."
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPROCESAR PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _run_reprocess_task():
    set_task_status("reprocess", "running", "Transformando datos...")
    try:
        subprocess.run([sys.executable, "src/transformer.py"], cwd=str(ROOT), timeout=120)
        set_task_status("reprocess", "running", "Cargando en BD...")
        subprocess.run([sys.executable, "src/loader.py"], cwd=str(ROOT), timeout=120)
        set_task_status("reprocess", "running", "Calculando S&OP...")
        subprocess.run([sys.executable, "src/planner.py"], cwd=str(ROOT), timeout=120)
        set_task_status("reprocess", "done", "Reprocesamiento completado con éxito.")
    except Exception as e:
        msg = f"Error en tarea de reprocesamiento: {e}"
        print(msg)
        set_task_status("reprocess", "error", msg)

@router.post("/reprocess")
async def reprocess(background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """Ejecuta transformer → planner en segundo plano."""
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(403, "Solo el admin puede reprocesar")

    background_tasks.add_task(_run_reprocess_task)
    return {
        "ok": True, 
        "msg": "El pipeline de reprocesamiento ha iniciado en segundo plano. Los datos se actualizarán pronto."
    }

@router.get("/task-status")
def get_task_status():
    """Retorna el estado actual de las tareas en segundo plano."""
    try:
        if TASK_STATUS_FILE.exists():
            return json.loads(TASK_STATUS_FILE.read_text())
    except Exception:
        pass
    return {}
