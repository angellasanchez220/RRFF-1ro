"""
transit_transformer.py — Motor de Tránsito RRFF Soft
======================================================
Submódulo del transformer: procesa las Órdenes de Compra Excel de
/data/manual_uploads/ordenes_compra/, cruza con dim_productos y
control_embarques.csv, aplica buffer de aforo (+14 días) y genera
transito_clean.csv en /data/processed.

Flujo:
  1. Escanea /data/manual_uploads/ordenes_compra/ buscando *.xlsx / *.xls
  2. Por cada archivo: detecta y lee la tabla de OC (CODIGO_FEMACO + CANTIDAD_OC)
  3. Cruza con dim_productos (SQL) para obtener el SKU universal
  4. Cruza con control_embarques.csv para inyectar/sobrescribir codigo_envio + fecha_eta
  5. Suma 14 días de Buffer de Aforo → fecha_disponibilidad_real
  6. Consolida todos los archivos y exporta transito_clean.csv

Estructura esperada del Excel OC (flexible, detección automática de columnas):
  CODIGO_FEMACO  —  llave de cruce con dim_productos
  CANTIDAD_OC    —  unidades en tránsito
  (opcionales: DESCRIPCION, N_OC, ETA_EXCEL, etc.)

Columnas de transito_clean.csv:
  nombre_archivo | codigo_femaco | sku | nombre_producto | cantidad_transito
  codigo_envio | fecha_eta | fecha_disponibilidad_real | origen_eta
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
OC_DIR      = BASE_DIR / "data" / "manual_uploads" / "ordenes_compra"
CTRL_FILE   = BASE_DIR / "data" / "manual_uploads" / "control_embarques.csv"
PROC_DIR    = BASE_DIR / "data" / "processed"

BUFFER_AFORO_DIAS = 14   # Días de aforo aduanero a sumar siempre

# Variantes de nombre de columna aceptadas (case-insensitive)
COL_VARIANTES_CODIGO = ["codigo_femaco", "cod_femaco", "codigo", "code", "ref", "referencia"]
COL_VARIANTES_QTY    = ["cantidad_oc", "cantidad", "qty", "units", "unidades", "cant"]
COL_VARIANTES_ETA    = ["eta", "fecha_eta", "eta_estimada", "eta_excel", "fecha_llegada"]

log = logging.getLogger("transit")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalizar_col(nombre: str) -> str:
    """Normaliza un nombre de columna para comparación."""
    import re
    return re.sub(r"[\s\-/]+", "_", nombre.lower()).strip("_")


def _encontrar_col(df: pd.DataFrame, variantes: list[str]) -> str | None:
    """Devuelve la primera columna que coincida con alguna variante."""
    cols_norm = {_normalizar_col(c): c for c in df.columns}
    for v in variantes:
        if v in cols_norm:
            return cols_norm[v]
    return None


def _leer_oc_excel(path: Path) -> pd.DataFrame | None:
    """
    Lee un Excel de OC con detección flexible de headers.
    Busca la fila que contiene CODIGO_FEMACO y usa esa como header.
    Retorna None si no puede leer.
    """
    try:
        # Leer sin headers para buscar la fila de cabecera
        raw = pd.read_excel(path, sheet_name=0, header=None, engine="openpyxl")
    except Exception as exc:
        log.warning("No se pudo abrir %s: %s", path.name, exc)
        return None

    # Buscar la fila que contiene 'CODIGO_FEMACO' o variantes
    header_row = None
    for i, row in raw.iterrows():
        row_str = " ".join(str(v).lower() for v in row.values)
        if any(v in row_str for v in ["codigo_femaco", "cod_femaco", "codigo"]):
            header_row = i
            break

    if header_row is None:
        log.warning("No se encontro fila de cabecera en %s. Se omite.", path.name)
        return None

    # Releer con header correcto
    df = pd.read_excel(path, sheet_name=0, header=header_row, engine="openpyxl")

    # Normalizar nombres de columna
    df.columns = [_normalizar_col(str(c)) for c in df.columns]

    # Identificar columnas clave
    col_cod = _encontrar_col(df, COL_VARIANTES_CODIGO)
    col_qty = _encontrar_col(df, COL_VARIANTES_QTY)

    if not col_cod or not col_qty:
        log.warning("Columnas CODIGO_FEMACO / CANTIDAD_OC no encontradas en %s. "
                    "Cols disponibles: %s", path.name, list(df.columns))
        return None

    # Columna ETA opcional desde el Excel
    col_eta = _encontrar_col(df, COL_VARIANTES_ETA)

    # Seleccionar y renombrar columnas clave
    cols_keep = {col_cod: "codigo_femaco", col_qty: "cantidad_oc"}
    if col_eta:
        cols_keep[col_eta] = "eta_excel"
    df = df[list(cols_keep.keys())].rename(columns=cols_keep)

    # Limpiar: eliminar filas sin código o sin cantidad
    df["codigo_femaco"] = df["codigo_femaco"].astype(str).str.strip()
    df["cantidad_oc"]   = pd.to_numeric(df["cantidad_oc"], errors="coerce")
    df = df.dropna(subset=["codigo_femaco", "cantidad_oc"])
    df = df[df["codigo_femaco"].str.len() > 0]
    df = df[df["cantidad_oc"] > 0]

    df["nombre_archivo"] = path.name
    log.info("  OC '%s': %d líneas válidas leídas.", path.name, len(df))
    return df


def _cargar_control_embarques() -> pd.DataFrame:
    """Lee control_embarques.csv. Devuelve DataFrame vacío si no existe."""
    if not CTRL_FILE.exists():
        log.warning("control_embarques.csv no encontrado en %s. "
                    "Se usarán solo ETAs del Excel.", CTRL_FILE.parent)
        return pd.DataFrame(columns=["nombre_archivo_excel", "codigo_envio", "fecha_eta"])
    try:
        df = pd.read_csv(CTRL_FILE, encoding="utf-8-sig")
        df.columns = df.columns.str.strip().str.lower()
        df["nombre_archivo_excel"] = df["nombre_archivo_excel"].astype(str).str.strip()
        log.info("control_embarques.csv: %d entradas cargadas.", len(df))
        return df
    except Exception as exc:
        log.error("Error leyendo control_embarques.csv: %s", exc)
        return pd.DataFrame(columns=["nombre_archivo_excel", "codigo_envio", "fecha_eta"])


def _cruzar_con_dim_productos(df_oc: pd.DataFrame, engine) -> pd.DataFrame:
    """
    Cruza codigo_femaco con dim_productos para obtener el SKU universal.
    Los códigos sin match en dim_productos se conservan con sku=None (se reportan).
    """
    dim = pd.read_sql(
        "SELECT sku, codigo_femaco, nombre_producto FROM dim_productos",
        engine
    )
    dim["codigo_femaco"] = dim["codigo_femaco"].astype(str).str.strip()
    df_oc["codigo_femaco"] = df_oc["codigo_femaco"].astype(str).str.strip()

    merged = df_oc.merge(dim, on="codigo_femaco", how="left")

    sin_sku = merged[merged["sku"].isna()]
    if len(sin_sku) > 0:
        log.warning("  %d código(s) FEMACO sin match en dim_productos: %s",
                    len(sin_sku), sin_sku["codigo_femaco"].tolist())

    con_sku = merged[merged["sku"].notna()]
    log.info("  Cruce dim_productos: %d/%d líneas con SKU válido.",
             len(con_sku), len(merged))
    return merged


def _aplicar_control_embarques(df: pd.DataFrame, df_ctrl: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza con control_embarques.csv usando nombre_archivo como llave.
    La ETA de control_embarques SOBRESCRIBE la ETA del Excel si existe.
    Origen del ETA queda registrado en la columna 'origen_eta'.
    """
    if df_ctrl.empty:
        df["codigo_envio"] = None
        df["fecha_eta_ctrl"] = None
    else:
        df_ctrl = df_ctrl.rename(columns={
            "nombre_archivo_excel": "nombre_archivo",
            "fecha_eta": "fecha_eta_ctrl"
        })
        df = df.merge(df_ctrl, on="nombre_archivo", how="left")

    # Determinar ETA final: control_embarques > eta_excel > None
    def _resolver_eta(row):
        eta_ctrl = row.get("fecha_eta_ctrl")
        eta_xl   = row.get("eta_excel")

        if pd.notna(eta_ctrl) and str(eta_ctrl).strip():
            try:
                return pd.Timestamp(str(eta_ctrl).strip()), "control_embarques"
            except Exception:
                pass
        if pd.notna(eta_xl) and str(eta_xl).strip():
            try:
                return pd.Timestamp(str(eta_xl).strip()), "excel_oc"
            except Exception:
                pass
        return None, "sin_eta"

    resultados = df.apply(_resolver_eta, axis=1, result_type="expand")
    df["fecha_eta"]   = resultados[0]
    df["origen_eta"]  = resultados[1]
    return df


def _aplicar_buffer_aforo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Suma BUFFER_AFORO_DIAS días a fecha_eta para obtener fecha_disponibilidad_real.
    Si fecha_eta es nula, fecha_disponibilidad_real también queda nula.
    """
    df["fecha_disponibilidad_real"] = df["fecha_eta"].apply(
        lambda eta: (eta + timedelta(days=BUFFER_AFORO_DIAS)).date()
        if pd.notna(eta) else None
    )
    df["fecha_eta"] = df["fecha_eta"].apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────────────────────────────────────

def procesar_transito(engine) -> pd.DataFrame | None:
    """
    Ejecuta el flujo completo de procesamiento de tránsito.

    Args:
        engine: SQLAlchemy engine con conexión a RRFF_AS_db.

    Returns:
        DataFrame consolidado de tránsito (puede estar vacío si no hay OCs),
        o None si ocurrió un error crítico.
    """
    log.info("--- [2e] Procesando: Órdenes de Compra en Tránsito ---")

    OC_DIR.mkdir(parents=True, exist_ok=True)

    # ── Escanear archivos OC ──────────────────────────────────────────────────
    archivos = sorted([f for f in OC_DIR.iterdir()
                       if f.suffix.lower() in (".xlsx", ".xls")])

    if not archivos:
        log.info("  No se encontraron Excels de OC en %s. "
                 "transito_clean.csv generado vacío.", OC_DIR)
        df_vacio = pd.DataFrame(columns=[
            "nombre_archivo", "codigo_femaco", "sku", "nombre_producto",
            "cantidad_transito", "codigo_envio", "fecha_eta",
            "fecha_disponibilidad_real", "origen_eta"
        ])
        return df_vacio

    log.info("  Archivos OC encontrados: %d — %s",
             len(archivos), [f.name for f in archivos])

    # ── Leer y consolidar todos los Excels ────────────────────────────────────
    dfs = []
    for archivo in archivos:
        df_oc = _leer_oc_excel(archivo)
        if df_oc is not None:
            dfs.append(df_oc)

    if not dfs:
        log.warning("  Ningún archivo OC pudo leerse. transito_clean.csv vacío.")
        return pd.DataFrame()

    df_all = pd.concat(dfs, ignore_index=True)
    log.info("  Total líneas OC consolidadas: %d", len(df_all))

    # ── Cruce con dim_productos ───────────────────────────────────────────────
    df_all = _cruzar_con_dim_productos(df_all, engine)

    # ── Cruce con control_embarques.csv ───────────────────────────────────────
    df_ctrl = _cargar_control_embarques()
    df_all  = _aplicar_control_embarques(df_all, df_ctrl)

    # ── Buffer de aforo ───────────────────────────────────────────────────────
    df_all = _aplicar_buffer_aforo(df_all)

    # ── Renombrar y seleccionar columnas finales ───────────────────────────────
    df_final = df_all.rename(columns={"cantidad_oc": "cantidad_transito"})

    cols_finales = [
        "nombre_archivo", "codigo_femaco", "sku", "nombre_producto",
        "cantidad_transito", "codigo_envio", "fecha_eta",
        "fecha_disponibilidad_real", "origen_eta"
    ]
    # Añadir sólo columnas que existen
    cols_presentes = [c for c in cols_finales if c in df_final.columns]
    df_final = df_final[cols_presentes].copy()

    # ── Logging de resultado ──────────────────────────────────────────────────
    log.info("  Tránsito procesado: %d líneas | %d SKUs únicos con ETA",
             len(df_final),
             df_final["sku"].notna().sum())
    log.info("  Fecha ETA origen: %s",
             df_final["origen_eta"].value_counts().to_dict() if "origen_eta" in df_final else "N/A")

    if "fecha_disponibilidad_real" in df_final.columns:
        sample = df_final[df_final["sku"].notna()].head(3)
        for _, r in sample.iterrows():
            log.info("    SKU %-10s | qty=%4.0f | ETA=%s | Disponible=%s (+14d aforo)",
                     r.get("sku", "N/A"), r.get("cantidad_transito", 0),
                     r.get("fecha_eta", "N/A"), r.get("fecha_disponibilidad_real", "N/A"))

    return df_final
