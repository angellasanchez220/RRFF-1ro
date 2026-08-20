"""
transformer.py — Motor de Transformación RRFF Soft
===================================================
Fase 2 del orquestador: lee los CSVs descargados por el extractor desde
/data/raw, procesa el inventario manual desde /data/manual_uploads, aplica
limpieza estructural y produce los DataFrames consolidados en /data/processed.

Flujos de procesamiento:
  2a. Maestro de Productos    → maestro_productos_clean.csv
  2b. Ventas Semanales        → ventas_semanales_clean.csv
  2c. Inventario Manual Excel → inventario_stock_clean.csv
  2d. Join consolidado        → maestro_consolidado.csv
  2e. Órdenes de Compra OC   → transito_clean.csv
                                 (OC Excel → SKU via dim_productos, ETA + 14d aforo)
  2f. Estado Inventario HC    → estado_inventario_hc_clean.csv
                                 (Stock por tienda/HC desde Shiny Datos app)

Transformaciones aplicadas:
  1. Auto-detección de formato CSV (sep, encoding)
  2. Estandarización de nombres de columnas (minúsculas + guiones_bajos)
  3. Eliminación de registros completamente vacíos
  4. Normalización de separadores numéricos (coma/punto)
  5. Escaneo de /data/manual_uploads: hoja 'INVENTARIO FINAL', cols B(SKU) y E(STOCK ACT)
  6. Left join Maestro ← Inventario por SKU
  7. Informe de calidad por DataFrame

Dependencias: pandas, openpyxl
"""

import logging
from pathlib import Path

import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).resolve().parent.parent
RAW_DIR       = BASE_DIR / "data" / "raw"
PROC_DIR      = BASE_DIR / "data" / "processed"
MANUAL_DIR    = BASE_DIR / "data" / "manual_uploads"

PROC_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Parámetros de lectura (detectados en perfilado de datos 2026-05-11)
# ──────────────────────────────────────────────────────────────────────────────

# Parámetros base de lectura (detectados en perfilado 2026-05-11)
# El separador real se auto-detecta por archivo (ver _detect_csv_params)
BASE_ENCODING = "utf-8-sig"   # Shiny exports — UTF-8 con BOM

# Columnas con coma decimal que requieren normalización (por nombre pre-estandarización)
COLS_DECIMAL_COMA_MAESTRO = ["Gancheras"]
COLS_DECIMAL_COMA_VENTAS  = ["OC_X_RECIBIR", "TRF ENVIADO"]  # formato Shiny download

# ── Inventario Manual (Excel) ─────────────────────────────────────────────────
INVENTARIO_SHEET_NAME = "INVENTARIO FINAL"   # nombre exacto de la hoja (4ta hoja)
INVENTARIO_COL_SKU    = "SKU"               # columna B — llave de join
INVENTARIO_COL_STOCK  = "STOCK ACT"         # columna E — valor a incorporar
INVENTARIO_HEADER_ROW = 2                   # fila 3 del libro (0-indexed = 2)

# ── Estado de Inventario HC (CSV desde Shiny) ─────────────────────────────────
# Columnas candidatas para Stock HC (se busca por nombre aproximado)
HC_COL_SKU_CANDIDATAS   = ["sku", "codigo", "cod"]
HC_COL_STOCK_CANDIDATAS = ["stock_fisico", "stock_hc", "stock_tiendas", "stock_hc_", "stock_fisico_hc",
                            "stock_disponible", "stock"]  # en orden de prioridad

# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TRANSFORMER] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("transformer")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _detect_csv_params(path: Path) -> dict:
    """
    Auto-detecta el separador y encoding del CSV inspeccionando las primeras lineas.
    Soporta:
      - Formato Shiny (sep=';', encoding='utf-8-sig', decimal=',')
      - Formato DataTable (sep=',', encoding='utf-8',  decimal='.' con miles='.')
    """
    # Intentar leer el inicio del archivo
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            with open(path, "r", encoding=enc) as f:
                first_line = f.readline(500)
            break
        except Exception:
            continue
    else:
        first_line = ""
        enc = "utf-8"

    # Detectar separador contando ocurrencias en la primera linea
    n_semis  = first_line.count(";")
    n_commas = first_line.count(",")

    if n_semis > n_commas:
        sep = ";"
        # Shiny: decimales con coma, miles sin separador
        fmt = "shiny"
    else:
        sep = ","
        # DataTable: miles con punto ("1.295" = 1295), sin separador decimal real
        fmt = "datatable"

    log.info("  Formato detectado: %s  (sep='%s', enc='%s')", fmt, sep, enc)
    return {"sep": sep, "encoding": enc, "dtype": str, "fmt": fmt}

def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estandariza los nombres de columnas:
      - Convierte a minúsculas
      - Reemplaza espacios y barras por guiones_bajos
      - Elimina caracteres especiales residuales
      - Colapsa guiones_bajos múltiples
    """
    new_cols = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[\s/\-]+", "_", regex=True)      # espacios, /, - → _
        .str.replace(r"[^a-z0-9_áéíóúüñ]", "", regex=True)  # caracteres raros fuera
        .str.replace(r"_+", "_", regex=True)             # colapsar __ múltiples
        .str.strip("_")                                  # limpiar bordes
    )
    df.columns = new_cols
    return df


def _drop_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas donde TODOS los valores son NaN/vacíos."""
    before = len(df)
    df = df.dropna(how="all")
    dropped = before - len(df)
    if dropped:
        log.info("  Filas completamente vacías eliminadas: %d", dropped)
    return df.reset_index(drop=True)


def _fix_decimal_comma(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    En columnas con coma como separador decimal (formato español),
    reemplaza ',' por '.' y convierte a float.
    Solo actúa sobre columnas que existen en el DataFrame (post-estandarización).
    """
    for col in cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", ".", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
            log.info("  Columna '%s': decimal coma normalizado a float.", col)
    return df


def _quality_report(df: pd.DataFrame, nombre: str) -> None:
    """Imprime un resumen de calidad del DataFrame resultante."""
    n_filas, n_cols = df.shape
    n_nulos_total   = df.isnull().sum().sum()
    n_duplicados    = df.duplicated().sum()
    cols_con_nulos  = df.isnull().any()
    pct_nulos = (n_nulos_total / (n_filas * n_cols) * 100) if n_filas else 0

    log.info("  [%s] Shape: %d filas x %d columnas", nombre, n_filas, n_cols)
    log.info("  [%s] Nulos totales: %d (%.2f%%)", nombre, n_nulos_total, pct_nulos)
    log.info("  [%s] Filas duplicadas: %d", nombre, n_duplicados)
    if cols_con_nulos.any():
        cols_nulas = cols_con_nulos[cols_con_nulos].index.tolist()
        log.info("  [%s] Columnas con nulos: %s", nombre, cols_nulas)


# ──────────────────────────────────────────────────────────────────────────────
# Sub-transformaciones por reporte
# ──────────────────────────────────────────────────────────────────────────────

def _transform_maestro_productos() -> pd.DataFrame:
    """
    Carga y limpia el Maestro de Productos.

    Pasos específicos:
      1. Lectura base con parámetros detectados
      2. Estandarización de columnas
      3. Eliminación de filas vacías
      4. Normalización de decimales en columna 'gancheras'
      5. Informe de calidad
    """
    src = RAW_DIR / "maestro_productos.csv"
    log.info("Leyendo: %s", src)

    params = _detect_csv_params(src)
    params.pop("fmt")   # maestro siempre usa formato shiny
    df = pd.read_csv(src, **params)
    log.info("  Leido: %d filas x %d columnas", *df.shape)

    # 1. Estandarizar columnas
    df = _standardize_columns(df)
    log.info("  Columnas estandarizadas: %s", list(df.columns))

    # 2. Eliminar filas completamente vacías
    df = _drop_empty_rows(df)

    # 3. Normalizar decimal coma en 'gancheras'
    #    (el nombre ya está estandarizado en este punto)
    df = _fix_decimal_comma(df, ["gancheras"])

    # 4. Informe de calidad
    _quality_report(df, "maestro_productos")

    return df


def _transform_ventas_semanales() -> pd.DataFrame:
    """
    Carga y limpia el reporte de Ventas Semanales.

    Soporta dos formatos de origen:
      - Formato Shiny (45 cols, sep=';'):  descarga directa del servidor Shiny.
        Contiene columnas tanto de Ventas ($) como de Unidades.
      - Formato DataTable (9 cols, sep=','):  exportacion CSV del boton de la tabla.
        Solo contiene columnas visibles en modo Unidades + Stock Fisico.
        Miles separados por '.' ("17.948" = 17948).

    Transformaciones:
      1. Auto-deteccion de formato
      2. Estandarizacion de columnas
      3. Eliminacion de filas vacias
      4. Normalizacion de separadores numericos segun formato
      5. Informe de calidad
    """
    src = RAW_DIR / "ventas_semanales.csv"
    log.info("Leyendo: %s  (puede tardar segun el tamano)", src)

    params = _detect_csv_params(src)
    fmt    = params.pop("fmt")   # extraer flag de formato antes de pasar a read_csv

    df = pd.read_csv(src, **params)
    log.info("  Leido: %d filas x %d columnas", *df.shape)

    # 1. Estandarizar columnas
    df = _standardize_columns(df)
    log.info("  Columnas estandarizadas: %s", list(df.columns))

    # 2. Eliminar filas completamente vacias
    df = _drop_empty_rows(df)

    if fmt == "shiny":
        # ── Formato Shiny: 45 columnas, decimales con coma ────────────────────
        log.info("  Aplicando normalizacion formato Shiny (45 cols)...")
        df = _fix_decimal_comma(df, ["oc_x_recibir", "trf_enviado"])

        # Columnas numericas enteras conocidas
        cols_int = [
            "semana_actual", "local_id", "unidades_x_pallet",
            "stock_disponible", "trf_por_recibir",
            "ventas_semana_actual", "ventas_semana_1", "ventas_semana_2",
            "ventas_semana_3", "ventas_semana_4", "total_ventas_semanas_cerradas",
            "unidades_semana_actual", "unidades_semana_1", "unidades_semana_2",
            "unidades_semana_3", "unidades_semana_4", "total_unidades_semanas_cerradas",
            "reservado",
        ]
        for col in [c for c in cols_int if c in df.columns]:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        if "fecha_carga" in df.columns:
            df["fecha_carga"] = pd.to_datetime(df["fecha_carga"], errors="coerce")

    else:
        # ── Formato DataTable: 9 columnas, miles con punto ────────────────────
        # Ejemplo: "17.948" en la tabla = 17948 unidades (punto = separador de miles)
        log.info("  Aplicando normalizacion formato DataTable (columnas de unidades)...")
        cols_numericas = [c for c in df.columns if c not in ["sku", "producto"]]
        for col in cols_numericas:
            # Remover separador de miles (punto) y convertir a entero
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(".", "", regex=False)   # "17.948" → "17948"
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            log.info("  Columna '%s': miles normalizados a entero.", col)

    # 3. Informe de calidad
    _quality_report(df, "ventas_semanales")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Estado de Inventario HC (CSV desde extractor Shiny)
# ──────────────────────────────────────────────────────────────────────────────

def _transform_estado_inventario() -> pd.DataFrame | None:
    """
    Procesa el archivo ventas_semanales.csv descargado del Módulo 3 de Matrix
    para extraer el Stock Físico (Stock HC).
    Detecta automáticamente la columna de Stock HC buscando por nombres candidatos.

    Retorna DataFrame con columnas: ['sku', 'stock_hc']
    Retorna None si el archivo no existe o no tiene la columna.
    """
    src = RAW_DIR / "ventas_semanales.csv"
    if not src.exists():
        log.warning("ventas_semanales.csv no encontrado en RAW_DIR. Paso 2f omitido.")
        return None

    log.info("Leyendo: %s", src)
    params = _detect_csv_params(src)
    params.pop("fmt", None)
    df = pd.read_csv(src, **params)
    df = _standardize_columns(df)
    df = _drop_empty_rows(df)
    log.info("  Leido (bruto): %d filas x %d columnas", *df.shape)
    log.info("  Columnas disponibles: %s", list(df.columns))

    # --- Detectar columna SKU ---
    col_sku = None
    for cand in HC_COL_SKU_CANDIDATAS:
        if cand in df.columns:
            col_sku = cand
            break
    if col_sku is None:
        # Buscar por substring
        for c in df.columns:
            if any(k in c for k in ["sku", "cod"]):
                col_sku = c
                break
    if col_sku is None:
        log.error("No se encontro columna SKU en estado_inventario.csv. Columnas: %s", list(df.columns))
        return None
    log.info("  Columna SKU detectada: '%s'", col_sku)

    # --- Detectar columna Stock HC ---
    col_hc = None
    if len(df.columns) >= 9:
        col_hc = df.columns[8]  # Columna I en Excel
        log.info("  Usando Columna I (índice 8) para Stock HC: '%s'", col_hc)
    else:
        for cand in HC_COL_STOCK_CANDIDATAS:
            if cand in df.columns:
                col_hc = cand
                break
        if col_hc is None:
            # Buscar por substring que contenga 'stock'
            for c in df.columns:
                if "stock" in c:
                    col_hc = c
                    break
    if col_hc is None:
        log.error("No se encontro columna de Stock HC en estado_inventario.csv. Columnas: %s", list(df.columns))
        return None
    log.info("  Columna Stock HC detectada: '%s'", col_hc)

    # --- Extraer y limpiar ---
    df_hc = df[[col_sku, col_hc]].copy()
    df_hc.columns = ["sku", "stock_hc"]

    # Limpiar SKU
    df_hc["sku"] = (
        df_hc["sku"].astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    df_hc = df_hc[df_hc["sku"].notna() & (df_hc["sku"] != "") & (df_hc["sku"] != "nan")]

    # Normalizar stock_hc
    df_hc["stock_hc"] = (
        df_hc["stock_hc"].astype(str)
        .str.replace(".", "", regex=False)   # miles con punto
        .str.replace(",", ".", regex=False)  # decimal con coma
        .str.strip()
    )
    df_hc["stock_hc"] = pd.to_numeric(df_hc["stock_hc"], errors="coerce").fillna(0).astype(int)

    # Eliminar duplicados (conservar el último)
    df_hc = df_hc.drop_duplicates(subset="sku", keep="last").reset_index(drop=True)

    _quality_report(df_hc, "estado_inventario_hc")
    log.info("  Stock HC procesado: %d SKUs", len(df_hc))
    return df_hc



# ──────────────────────────────────────────────────────────────────────────────
# Inventario Manual (Excel /data/manual_uploads)
# ──────────────────────────────────────────────────────────────────────────────

def _scan_manual_uploads() -> Path | None:
    """
    Escanea /data/manual_uploads buscando el archivo Excel de inventario.
    Reglas de busqueda:
      - Extension .xlsx o .xls
      - Prioriza el archivo mas reciente si hay varios
      - Retorna None si el directorio esta vacio
    """
    candidatos = sorted(
        list(MANUAL_DIR.glob("*.xlsx")) + list(MANUAL_DIR.glob("*.xls")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,    # mas reciente primero
    )
    if not candidatos:
        log.warning("No se encontraron archivos Excel en %s", MANUAL_DIR)
        return None

    elegido = candidatos[0]
    if len(candidatos) > 1:
        log.warning(
            "Multiples archivos Excel en manual_uploads (%d). "
            "Usando el mas reciente: %s", len(candidatos), elegido.name
        )
    else:
        log.info("Archivo de inventario encontrado: %s", elegido.name)
    return elegido


def _read_inventario_excel(path: Path) -> pd.DataFrame:
    """
    Lee la hoja 'INVENTARIO FINAL' del libro Excel y extrae
    unicamente las columnas COD_CAJA (col A=0), SKU (col B=1) y STOCK ACT (col E=4).
    """
    log.info("Leyendo hoja de inventario desde: %s", path.name)

    xl = pd.ExcelFile(path)
    # Buscar hoja "INVENTARIO FINAL" (que es la hoja donde STOCK ACT esta en E)
    target_sheet = next((s for s in xl.sheet_names if "INVENTARIO FINAL" in s.upper()), None)
    
    if not target_sheet:
        hojas_disponibles = xl.sheet_names
        raise ValueError(
            f"La hoja 'INVENTARIO FINAL' no existe en el archivo '{path.name}'. "
            f"Hojas disponibles: {hojas_disponibles}"
        )

    # La cabecera en INVENTARIO FINAL esta en la fila 0
    df = xl.parse(sheet_name=target_sheet, header=0)
    if len(df.columns) < 5:
        df = xl.parse(sheet_name=target_sheet, header=1)
        if len(df.columns) < 5:
            df = xl.parse(sheet_name=target_sheet, header=None)

    col_caja = df.iloc[:, 0]
    col_sku = df.iloc[:, 1]
    col_stock = df.iloc[:, 4]

    # Consolidar SKU: Si B está vacío/nulo, usar A
    sku_final = col_sku.copy()
    mask_empty = sku_final.isna() | (sku_final.astype(str).str.strip() == "") | (sku_final.astype(str).str.strip().str.lower() == "nan") | (sku_final.astype(str).str.strip() == "0")
    sku_final.loc[mask_empty] = col_caja.loc[mask_empty]

    df_clean = pd.DataFrame({"sku": sku_final, "stock_act": col_stock})

    # Normalizar SKU: limpiar espacios, convertir a string puro
    df_clean["sku"] = df_clean["sku"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    # STOCK ACT: convertir a entero (admite NaN con Int64)
    df_clean["stock_act"] = pd.to_numeric(df_clean["stock_act"], errors="coerce").fillna(0).astype("Int64")
    
    # Eliminar filas vacías o nulas en SKU
    df_clean = df_clean[df_clean["sku"].notna() & (df_clean["sku"] != "") & (df_clean["sku"] != "nan") & (df_clean["sku"] != "0")]
    df_clean = df_clean.reset_index(drop=True)

    # Detectar y reportar duplicados de SKU en el inventario
    dups = df_clean[df_clean["sku"].duplicated(keep=False)]
    if not dups.empty:
        log.warning(
            "  SKUs duplicados en el inventario (%d filas). "
            "Se conservara el ultimo valor por SKU.", len(dups)
        )
        df_clean = df_clean.drop_duplicates(subset="sku", keep="last")

    log.info(
        "  Inventario limpio: %d SKUs con stock | Nulos en stock_act: %d",
        len(df_clean), df_clean["stock_act"].isna().sum()
    )
    return df_clean


def _merge_maestro_inventario(
    df_maestro: pd.DataFrame,
    df_inventario: pd.DataFrame,
) -> pd.DataFrame:
    """
    Realiza un LEFT JOIN entre el Maestro de Productos (base) y el
    DataFrame de inventario (stock), usando 'sku' como llave primaria.

    LEFT JOIN garantiza que:
      - Todos los SKUs del maestro aparecen en el resultado
      - SKUs sin stock en el inventario quedan con stock_act = NaN (ausente)
      - SKUs del inventario que no estan en el maestro se descartan

    El campo 'stock_act' se posiciona inmediatamente despues de 'nombre_producto'
    para maxima legibilidad en el output.
    """
    log.info("Ejecutando LEFT JOIN: Maestro de Productos <- Inventario (llave: sku)")

    # Normalizar tipo de SKU en maestro para asegurar compatibilidad de tipos
    # (maestro.sku = int/str, inventario.sku = str)
    df_maestro = df_maestro.copy()
    df_maestro["sku"] = df_maestro["sku"].astype(str).str.strip()

    df_result = df_maestro.merge(
        df_inventario[["sku", "stock_act"]],
        on="sku",
        how="left",
        validate="many_to_one",   # cada SKU del maestro matchea a maximo 1 fila del inventario
    )

    # Estadisticas del join
    total_maestro     = len(df_maestro)
    con_stock         = df_result["stock_act"].notna().sum()
    sin_stock         = df_result["stock_act"].isna().sum()
    skus_inventario   = len(df_inventario)
    skus_no_maestro   = skus_inventario - con_stock

    log.info("  SKUs en Maestro:          %d", total_maestro)
    log.info("  SKUs con stock_act:       %d  (%.1f%%)", con_stock,  con_stock  / total_maestro * 100)
    log.info("  SKUs sin stock_act (NaN): %d  (%.1f%%)", sin_stock, sin_stock / total_maestro * 100)
    log.info("  SKUs del inventario no presentes en Maestro (descartados): %d", skus_no_maestro)

    if sin_stock > 0:
        skus_faltantes = df_result.loc[df_result["stock_act"].isna(), "sku"].tolist()
        log.warning(
            "  Los siguientes SKUs del Maestro no tienen stock en el inventario: %s",
            skus_faltantes[:10]
        )

    # Reordenar columnas: sku | nombre_producto | stock_act | resto del maestro
    cols_base   = ["sku", "nombre_producto", "stock_act"]
    cols_resto  = [c for c in df_result.columns if c not in cols_base]
    df_result   = df_result[cols_base + cols_resto]

    return df_result


# ──────────────────────────────────────────────────────────────────────────────
# Bases Historicas
# ──────────────────────────────────────────────────────────────────────────────

def _transform_sellout_historico() -> pd.DataFrame:
    """
    Sell Out Historico — columnas por indice (estructura confirmada):
      C (idx 2) = Mes
      D (idx 3) = Ano
      N (idx13) = SKU
      U (idx20) = Cantidad (unidades vendidas)
    Agrupa por SKU+Ano+Mes sumando Cantidad.
    """
    path = RAW_DIR / "sellout_historico.csv"
    if not path.exists():
        log.warning("Archivo no encontrado: %s", path.name)
        return None

    log.info("Leyendo Sell Out Historico: %s", path)
    df = pd.read_csv(
        path, sep=";", encoding="utf-8-sig", dtype=str,
        quotechar='"', on_bad_lines="skip"
    )
    df = _drop_empty_rows(df)
    log.info("  Sell Out bruto: %d filas x %d columnas", *df.shape)

    if len(df.columns) < 21:
        log.warning("  Sell Out: columnas insuficientes (%d). Se omite.", len(df.columns))
        return None

    df_clean = pd.DataFrame()
    df_clean["sku"] = df.iloc[:, 13].astype(str).str.strip()   # N = SKU
    df_clean["ano"] = df.iloc[:,  3].astype(str).str.strip()   # D = Ano
    df_clean["mes"] = df.iloc[:,  2].astype(str).str.strip().str.lower()  # C = Mes
    # U = Cantidad (puede tener formato '12,00')
    uds = df.iloc[:, 20].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d.-]", "", regex=True)
    df_clean["unidades_sellout"] = pd.to_numeric(uds, errors="coerce").fillna(0).round(0).astype(int)

    df_clean = df_clean[
        df_clean["sku"].notna() & (df_clean["sku"] != "") & (df_clean["sku"] != "nan")
    ]

    df_grouped = df_clean.groupby(["sku", "ano", "mes"])["unidades_sellout"].sum().reset_index()
    df_grouped.rename(columns={"ano": "año"}, inplace=True)
    log.info("  Sell Out agrupado: %d combinaciones sku/ano/mes", len(df_grouped))
    return df_grouped


def _transform_sellin_historico() -> pd.DataFrame:
    """
    Sell In Historico — columnas por indice (estructura confirmada):
      E (idx 4) = Mes
      F (idx 5) = Ano
      N (idx13) = SKU
      U (idx20) = Unidades_Confirmadas  ← columna correcta (no Unidades_Informadas)
    Agrupa por SKU+Ano+Mes sumando Unidades_Confirmadas.
    """
    path = RAW_DIR / "sellin_historico.csv"
    if not path.exists():
        log.warning("Archivo no encontrado: %s", path.name)
        return None

    log.info("Leyendo Sell In Historico: %s", path)
    df = pd.read_csv(
        path, sep=";", encoding="utf-8-sig", dtype=str,
        quotechar='"', on_bad_lines="skip"
    )
    df = _drop_empty_rows(df)
    log.info("  Sell In bruto: %d filas x %d columnas", *df.shape)

    if len(df.columns) < 21:
        log.warning("  Sell In: columnas insuficientes (%d). Se omite.", len(df.columns))
        return None

    df_clean = pd.DataFrame()
    df_clean["sku"] = df.iloc[:, 13].astype(str).str.strip()              # N = SKU
    df_clean["ano"] = df.iloc[:,  5].astype(str).str.strip()              # F = Ano
    df_clean["mes"] = df.iloc[:,  4].astype(str).str.strip().str.lower()  # E = Mes
    # U = Unidades_Confirmadas (puede tener formato '12,00')
    uds = df.iloc[:, 20].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d.-]", "", regex=True)
    df_clean["unidades_sellin"] = pd.to_numeric(uds, errors="coerce").fillna(0).round(0).astype(int)

    df_clean = df_clean[
        df_clean["sku"].notna() & (df_clean["sku"] != "") & (df_clean["sku"] != "nan")
    ]

    df_grouped = df_clean.groupby(["sku", "ano", "mes"])["unidades_sellin"].sum().reset_index()
    df_grouped.rename(columns={"ano": "año"}, inplace=True)
    log.info("  Sell In agrupado: %d combinaciones sku/ano/mes", len(df_grouped))
    # Verificar dato del usuario: SKU 7064349 junio 2025
    check = df_grouped[
        (df_grouped["sku"] == "7064349") &
        (df_grouped["año"] == "2025") &
        (df_grouped["mes"] == "junio")
    ]
    if not check.empty:
        log.info("  VALIDACION: SKU 7064349 junio 2025 sellin=%s (esperado=10)",
                 check["unidades_sellin"].values[0])
    return df_grouped

# ──────────────────────────────────────────────────────────────────────────────
# Función principal exportada
# ──────────────────────────────────────────────────────────────────────────────

def run_transformation(archivos_raw=None):
    """
    Ejecuta el pipeline completo de transformacion (5 pasos):
      2a. Maestro de Productos    -> maestro_productos_clean.csv
      2b. Ventas Semanales        -> ventas_semanales_clean.csv
      2c. Inventario Manual Excel -> inventario_stock_clean.csv
      2d. Join consolidado        -> maestro_consolidado.csv
      2e. OC Transito             -> transito_clean.csv
    """
    import sys
    import os
    # Importar modulo de transito (mismo directorio /src)
    _src_dir = str(Path(__file__).resolve().parent)
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    from transit_transformer import procesar_transito
    from dotenv import load_dotenv
    from sqlalchemy import create_engine as _create_engine
    load_dotenv()
    import pandas as _pd

    log.info("=" * 60)
    log.info("FASE 2 - Motor de Transformacion iniciado")
    log.info("Fuente RAW:    %s", RAW_DIR)
    log.info("Fuente Manual: %s", MANUAL_DIR)
    log.info("Destino:       %s", PROC_DIR)
    log.info("=" * 60)

    resultados = {}
    df_maestro = None

    # -- 2a: Maestro de Productos
    log.info("--- [2a] Transformando: Maestro de Productos ---")
    try:
        df_maestro = _transform_maestro_productos()
        dest = PROC_DIR / "maestro_productos_clean.csv"
        df_maestro.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
        log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
        resultados["maestro_productos_clean.csv"] = dest
    except Exception as exc:
        log.error("Error en Maestro de Productos: %s", exc)
        resultados["maestro_productos_clean.csv"] = None

    # -- 2b: Ventas Semanales
    log.info("--- [2b] Transformando: Ventas Semanales ---")
    try:
        df_ventas = _transform_ventas_semanales()
        dest = PROC_DIR / "ventas_semanales_clean.csv"
        df_ventas.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
        log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
        resultados["ventas_semanales_clean.csv"] = dest
    except Exception as exc:
        log.error("Error en Ventas Semanales: %s", exc)
        resultados["ventas_semanales_clean.csv"] = None

    # -- 2c: Inventario Manual (Excel)
    log.info("--- [2c] Procesando: Inventario Manual (Excel) ---")
    df_inventario = None
    try:
        excel_path = _scan_manual_uploads()
        if excel_path is None:
            log.warning("Sin archivo Excel en manual_uploads. Consolidado sin stock_act.")
        else:
            df_inventario = _read_inventario_excel(excel_path)
            dest = PROC_DIR / "inventario_stock_clean.csv"
            df_inventario.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
            log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
            resultados["inventario_stock_clean.csv"] = dest
    except Exception as exc:
        log.error("Error en Inventario Manual: %s", exc)
        resultados["inventario_stock_clean.csv"] = None

    # -- 2d: Join Consolidado (Maestro + Stock)
    log.info("--- [2d] Generando: Maestro Consolidado (Maestro + Stock) ---")
    try:
        if df_maestro is None:
            raise RuntimeError("Maestro no procesado (paso 2a). No se puede consolidar.")

        if df_inventario is not None:
            df_consolidado = _merge_maestro_inventario(df_maestro, df_inventario)
        else:
            log.warning("Sin inventario disponible. stock_act = NaN para todos los SKUs.")
            df_consolidado = df_maestro.copy()
            df_consolidado["sku"] = df_consolidado["sku"].astype(str)
            df_consolidado.insert(2, "stock_act", _pd.NA)

        dest = PROC_DIR / "maestro_consolidado.csv"
        df_consolidado.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
        log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
        resultados["maestro_consolidado.csv"] = dest

        # Preview de validacion
        cols_preview = ["sku", "nombre_producto", "stock_act"]
        muestra = df_consolidado[cols_preview].head(5)
        log.info("  Preview consolidado (5 primeras filas):")
        for _, row in muestra.iterrows():
            log.info(
                "    SKU %-10s | %-40s | stock_act=%s",
                row["sku"], str(row["nombre_producto"])[:40], row["stock_act"]
            )

    except Exception as exc:
        log.error("Error en Join Consolidado: %s", exc)
        resultados["maestro_consolidado.csv"] = None

    # -- 2e: Transito (OC en tránsito)
    log.info("--- [2e] Procesando: OC Transito (maritime/terrestrial) ---")
    try:
        _db_url = os.getenv("DATABASE_URL")
        if _db_url:
            if _db_url.startswith("postgres://"):
                _db_url = _db_url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif _db_url.startswith("postgresql://"):
                _db_url = _db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
            _engine_tr = _create_engine(_db_url, connect_args={"connect_timeout": 10})
        else:
            _host = os.getenv("DB_HOST", "localhost").strip().strip('"')
            _port = os.getenv("DB_PORT", "5432").strip().strip('"')
            _name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
            _user = os.getenv("DB_USER", "postgres").strip().strip('"')
            _pwd  = os.getenv("DB_PASS", "postgres").strip().strip('"')
            _engine_tr = _create_engine(
                f"postgresql+psycopg2://{_user}:{_pwd}@{_host}:{_port}/{_name}",
                connect_args={"connect_timeout": 10},
            )
        df_transito = procesar_transito(_engine_tr)
        _engine_tr.dispose()

        if df_transito is not None:
            dest = PROC_DIR / "transito_clean.csv"
            df_transito.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
            log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
            resultados["transito_clean.csv"] = dest
        else:
            resultados["transito_clean.csv"] = None
    except Exception as exc:
        log.error("Error en OC Transito: %s", exc)
        resultados["transito_clean.csv"] = None

    # -- 2f: Estado de Inventario HC (desde extractor Shiny)
    log.info("--- [2f] Procesando: Estado de Inventario HC (Stock HC) ---")
    try:
        df_hc = _transform_estado_inventario()
        if df_hc is not None:
            dest = PROC_DIR / "estado_inventario_hc_clean.csv"
            df_hc.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
            log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
            resultados["estado_inventario_hc_clean.csv"] = dest
        else:
            log.warning("estado_inventario.csv no disponible. Stock HC no procesado.")
            resultados["estado_inventario_hc_clean.csv"] = None
    except Exception as exc:
        log.error("Error en Estado Inventario HC: %s", exc)
        resultados["estado_inventario_hc_clean.csv"] = None

    # -- 2g: Sell Out Historico
    log.info("--- [2g] Procesando: Sell Out Historico ---")
    try:
        df_so = _transform_sellout_historico()
        if df_so is not None:
            dest = PROC_DIR / "sellout_historico_clean.csv"
            df_so.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
            log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
            resultados["sellout_historico_clean.csv"] = dest
        else:
            resultados["sellout_historico_clean.csv"] = None
    except Exception as exc:
        log.error("Error en Sell Out Historico: %s", exc)
        resultados["sellout_historico_clean.csv"] = None

    # -- 2h: Sell In Historico
    log.info("--- [2h] Procesando: Sell In Historico ---")
    try:
        df_si = _transform_sellin_historico()
        if df_si is not None:
            dest = PROC_DIR / "sellin_historico_clean.csv"
            df_si.to_csv(dest, index=False, encoding="utf-8-sig", sep=";")
            log.info("Guardado: %s  (%d bytes)", dest, dest.stat().st_size)
            resultados["sellin_historico_clean.csv"] = dest
        else:
            resultados["sellin_historico_clean.csv"] = None
    except Exception as exc:
        log.error("Error en Sell In Historico: %s", exc)
        resultados["sellin_historico_clean.csv"] = None

    # -- Resumen final
    log.info("=" * 60)
    log.info("RESUMEN DE TRANSFORMACION:")
    exitos   = [k for k, v in resultados.items() if v is not None]
    fallidos = [k for k, v in resultados.items() if v is None]
    for nombre in exitos:
        log.info("  OK     %s", nombre)
    for nombre in fallidos:
        log.warning("  FALLO  %s", nombre)
    log.info("Total: %d/%d archivos procesados.", len(exitos), len(resultados))
    log.info("=" * 60)

    if resultados.get("maestro_consolidado.csv") is None:
        raise RuntimeError(
            "maestro_consolidado.csv no pudo generarse. Revisa los logs anteriores."
        )

    return resultados


if __name__ == "__main__":
    import sys
    try:
        archivos = run_transformation()
        print("\nArchivos procesados:")
        for nombre, ruta in archivos.items():
            print(f"  - {nombre}  ->  {ruta}")
        sys.exit(0)
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)
