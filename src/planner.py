"""
planner.py — Módulo de Inteligencia SOP RRFF Soft
===================================================
Fase 4 del orquestador: extrae datos de PostgreSQL (dim_productos + fact_ventas),
aplica lógica de planificación S&OP y persiste la tabla planificacion_sop.

LÓGICA IMPLEMENTADA:
  Paso 1 — Conexión y cruce: JOIN dim_productos ⋈ fact_ventas por SKU
  Paso 2 — Base transaccional 4 semanas:
            • Unidades individuales sem 1-4 (semanas cerradas)
            • Total ventas 4 semanas = ritmo de salida actual (sell-out rate)
            • La semana parcial (sem actual) se excluye del ritmo base
  Paso 3 — Matriz 12 meses (Sell-Out y Sell-In proyectados):
            • Sell-Out mensual = (ritmo_4_sem / 4) × semanas_del_mes
              con trigger de actualización: el mes anterior solo se actualiza
              el día 1 del mes siguiente (datos de may-2026 se fijan el 1-jun-2026)
            • Sell-In mensual = Sell-Out + buffer_reposicion (14 días = 2 semanas)
  Paso 4 — Inteligencia Comparativa:
            • YoY estimado: comparación del sell-out mensual actual
              vs mismo mes año anterior (usando factor de tendencia del catálogo)
            • Mes Pico Sell-Out: mes con mayor proyección de salida
            • Mes Pico Sell-In:  mes con mayor sugerencia de compra
  Paso 5 — Sell-In Ajustado (UMP):
            • sell_in_ajustado = math.ceil(sell_in / ump) * ump  (múltiplo estricto hacia arriba)
            • Si ump es None/0, se usa el sell_in sin ajuste
  Paso 6 — Persistencia: sobreescribe planificacion_sop en PostgreSQL
  Paso 7 — Métricas complementarias: sellout_minimo (mínimo de las 4 semanas × 4.33)

NOTA SOBRE PRECIOS:
  El pipeline actual no incluye precio unitario en las tablas cargadas.
  El campo 'monto_total_4_sem' se calcula como placeholder con precio=0
  hasta que se integre la tabla de precios (lista_precios o maestro completo).
  Se incluye la columna para cumplir el esquema definido.

Dependencias: sqlalchemy, psycopg2-binary, pandas, python-dotenv
"""

import logging
import math
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

TABLA_DIM       = "dim_productos"
TABLA_FACT      = "fact_ventas"
TABLA_PLAN      = "planificacion_sop"
CHUNK_SIZE      = 500

# Las semanas se detectan DINÁMICAMENTE desde fact_ventas en tiempo de ejecución.
# (El reporte Shiny rota cada semana, añadiendo una columna nueva al CSV de ventas)
# Patrón: columnas que empiecen con 'unidades' seguido de fecha, excepto
# 'total_unidades_semanas_cerradas' que es la suma acumulada.
COLS_SEM_PATTERN    = "unidades"         # prefijo de las columnas de semanas
COLS_SEM_EXCLUIR    = {                  # columnas que NO son semanas individuales
    "total_unidades_semanas_cerradas"
}
# Número de semanas cerradas a usar como base de ritmo
N_SEMANAS_BASE = 4

# Semanas por mes calendario (aproximación estándar para proyección)
SEMANAS_POR_MES = {
    1: 4.33, 2: 4.00, 3: 4.33, 4: 4.00,
    5: 4.33, 6: 4.33, 7: 4.33, 8: 4.33,
    9: 4.33, 10: 4.33, 11: 4.33, 12: 4.33,
}

# Factor de estacionalidad mensual relativo a Mayo
# (índice base = 1.0 para Mayo; valores derivados de patrones ferretería retail Chile)
ESTACIONALIDAD = {
    1: 0.95,   # Enero     — inicio año, demanda moderada
    2: 1.00,   # Febrero   — vuelta a clases + remodelaciones
    3: 1.10,   # Marzo     — peak post-verano, pre-otoño
    4: 1.05,   # Abril     — actividad alta
    5: 1.00,   # Mayo      — BASE (mes actual del dataset)
    6: 0.90,   # Junio     — invierno, caída moderada
    7: 0.85,   # Julio     — vacaciones invierno, menor actividad
    8: 0.92,   # Agosto    — recuperación gradual
    9: 1.08,   # Septiembre — peak Fiestas Patrias + remodelaciones
    10: 1.05,  # Octubre   — post-fiestas, demanda sostenida
    11: 1.10,  # Noviembre — Black Friday + inicio ciclo navideño
    12: 0.95,  # Diciembre — Navidad, cierre año
}

# Buffer de reposición en semanas (Lead Time + Safety Stock = 2 semanas)
BUFFER_SEMANAS_REPOSICION = 2.0

# Fecha de referencia (mes base del dataset)
# Se usa el mes y año actual dinámicamente para que sincronice correctamente 
# con la lógica de api/routes/sop.py que lee los últimos 12 meses.
_hoy = date.today()
MES_BASE         = _hoy.month
ANIO_BASE        = _hoy.year

# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PLANNER] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("planner")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_engine():
    """Construye el engine SQLAlchemy desde las credenciales del .env."""
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        engine = create_engine(db_url, connect_args={"connect_timeout": 10}, pool_pre_ping=True)
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT version()")).scalar()
            log.info("Conexion OK via DATABASE_URL: %s", ver[:55])
        return engine

    host = os.getenv("DB_HOST", "localhost").strip().strip('"')
    port = os.getenv("DB_PORT", "5432").strip().strip('"')
    name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
    user = os.getenv("DB_USER", "postgres").strip().strip('"')
    pwd_env = os.getenv("DB_PASS")
    if not pwd_env:
        raise RuntimeError("Falta DB_PASS; configura DATABASE_URL o las variables DB_*")
    pwd = pwd_env.strip().strip('"')
    url  = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
    engine = create_engine(url, connect_args={"connect_timeout": 10}, pool_pre_ping=True)
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version()")).scalar()
        log.info("Conexion OK: %s", ver[:55])
    return engine


def _ceil_to_multiple(value: float, multiple: float) -> float:
    """
    Redondea 'value' al próximo múltiplo exacto de 'multiple' (hacia arriba).
    Si multiple <= 0 o es None, retorna value sin cambios.
    """
    if not multiple or multiple <= 0 or math.isnan(multiple):
        return value
    return math.ceil(value / multiple) * multiple


def _trigger_update_ok(mes: int, anio: int, hoy: date) -> bool:
    """
    Trigger de actualización: el mes anterior solo se 'cierra' y actualiza
    el día 1 del mes siguiente.
    Ejemplo: datos de Mayo 2026 solo se actualizan desde el 01-Jun-2026.

    Retorna True si el mes ya está disponible para actualización.
    """
    # Calcular el primer día del mes siguiente al (mes, anio) dado
    if mes == 12:
        fecha_cierre = date(anio + 1, 1, 1)
    else:
        fecha_cierre = date(anio, mes + 1, 1)
    return hoy >= fecha_cierre


def _nombre_mes(num: int) -> str:
    """Retorna el nombre en español del mes (1→Enero, ..., 12→Diciembre)."""
    nombres = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
               "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    return nombres[num - 1]


# ──────────────────────────────────────────────────────────────────────────────
# Paso 1 — Extracción y cruce
# ──────────────────────────────────────────────────────────────────────────────

def _detectar_columnas_semana(engine) -> tuple[list[str], str | None]:
    """
    Detecta dinámicamente las columnas de semana cerradas en fact_ventas.
    Retorna:
      - cols_cerradas: lista de N_SEMANAS_BASE columnas más recientes (cerradas)
      - col_parcial:   columna de la semana en curso (la más nueva), o None
    """
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)
    todas_cols = [c["name"] for c in insp.get_columns(TABLA_FACT)]

    # Filtrar columnas de semana individuales (excluye totales y no-semana)
    cols_sem = sorted([
        c for c in todas_cols
        if c.startswith(COLS_SEM_PATTERN) and c not in COLS_SEM_EXCLUIR
    ])

    # La última columna es la semana parcial (en curso), las anteriores son cerradas
    if len(cols_sem) <= N_SEMANAS_BASE:
        cols_cerradas = cols_sem
        col_parcial   = None
    else:
        # Tomamos las últimas N+1, separamos la más nueva como parcial
        recientes     = cols_sem[-(N_SEMANAS_BASE + 1):]
        col_parcial   = recientes[-1]       # semana en curso (parcial)
        cols_cerradas = recientes[:-1]      # N semanas cerradas

    log.info("Semanas cerradas detectadas (%d): %s", len(cols_cerradas), cols_cerradas)
    if col_parcial:
        log.info("Semana parcial (excluida del ritmo): %s", col_parcial)

    return cols_cerradas, col_parcial


def _extraer_datos(engine) -> pd.DataFrame:
    """
    LEFT JOIN dim_productos ⋈ fact_ventas por SKU.
    Detecta dinámicamente las columnas de semana disponibles.
    Se excluye la fila 'Total' de fact_ventas (sku IS NULL).
    """
    log.info("Extrayendo cruce dim_productos x fact_ventas...")

    # Detectar columnas de semana disponibles
    cols_cerradas, col_parcial = _detectar_columnas_semana(engine)

    if len(cols_cerradas) < 2:
        raise RuntimeError(
            f"fact_ventas tiene menos de 2 semanas cerradas detectadas: {cols_cerradas}. "
            "Verifica que la Fase 3 (loader) se ejecutó correctamente."
        )

    # Construir SELECT dinámico para las semanas cerradas
    # Siempre se nombran sem1..semN en orden cronológico
    sem_select = "\n".join(
        f"            f.{col}  AS sem{i+1}_uds,"
        for i, col in enumerate(cols_cerradas)
    )
    parcial_select = (
        f"            f.{col_parcial}  AS sem_actual_uds,"
        if col_parcial else
        "            NULL::float8       AS sem_actual_uds,"
    )

    query_str = f"""
        SELECT
            d.sku,
            d.nombre_producto,
            d.codigo_femaco,
            d.categoria,
            d.subcategoria,
            d.formato,
            d.estado,
            COALESCE(d.stock_act, 0)           AS stock_act,
            COALESCE(d.ump, d.gancheras, 0)    AS ump,
{sem_select}
{parcial_select}
            f.total_unidades_semanas_cerradas  AS total_4_sem_uds,
            f.stock_fsico                      AS stock_fisico_matrix,
            COALESCE(t.cantidad_transito, 0)   AS cantidad_transito,
            t.eta_proxima                      AS eta_proxima
        FROM dim_productos d
        LEFT JOIN fact_ventas f ON d.sku = f.sku
        LEFT JOIN (
            SELECT sku, SUM(cantidad) AS cantidad_transito,
                   MIN(COALESCE(eta_ajustada, fecha_disponibilidad_real, fecha_eta)) AS eta_proxima
            FROM control_embarques
            WHERE estado IN ('EN_TRANSITO', 'EN_AFORO', 'RETRASADO')
            GROUP BY sku
        ) t ON d.sku = t.sku
        ORDER BY d.sku
    """

    df = pd.read_sql(text(query_str), engine)

    # Normalizar: asegurar que sem1..sem4 existen (rellenar con 0 si faltan)
    for i in range(1, N_SEMANAS_BASE + 1):
        col = f"sem{i}_uds"
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    log.info("Cruce extraido: %d filas x %d columnas", *df.shape)
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Paso 2 — Base transaccional 4 semanas
# ──────────────────────────────────────────────────────────────────────────────

def _calcular_base_transaccional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula métricas de ritmo de salida basadas en las 4 semanas cerradas.

    Columnas añadidas:
      - ritmo_semanal_uds:       promedio de las 4 semanas (base para proyectar)
      - total_4_sem_verificado:  suma directa de sem1..sem4 (auditoría)
      - sellout_minimo:          mínimo semanal × 4.33 → piso mensual real de demanda
      - monto_total_4_sem:       placeholder 0.0 (sin precio disponible)
    """
    cols_sem = ["sem1_uds", "sem2_uds", "sem3_uds", "sem4_uds"]
    for col in cols_sem:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Total de las 4 semanas cerradas (ritmo base, NO se usa promedio como ritmo)
    df["total_4_sem_verificado"] = df[cols_sem].sum(axis=1)

    # Ritmo semanal = total / 4 (base para proyectar a N semanas)
    df["ritmo_semanal_uds"] = df["total_4_sem_verificado"] / 4.0

    # Sell-Out Mínimo: mínimo semanal escalado al mes → piso de demanda real
    # Permite detectar SKUs con demanda irregular o estacional baja
    df["sellout_minimo"] = (df[cols_sem].min(axis=1) * 4.33).round(0)

    # Monto total: sin precio disponible en este pipeline → se deja en 0
    df["monto_total_4_sem"] = 0.0

    log.info(
        "Base transaccional calculada. Ritmo semanal promedio: %.1f uds/sem | "
        "Sell-Out Mínimo promedio: %.1f uds/mes",
        df["ritmo_semanal_uds"].mean(),
        df["sellout_minimo"].mean(),
    )
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Paso 3 — Proyección mensual 12 meses (Sell-Out y Sell-In)
# ──────────────────────────────────────────────────────────────────────────────

def _proyectar_12_meses(df: pd.DataFrame, hoy: date) -> tuple[pd.DataFrame, list]:
    """
    Genera la matriz de proyecciones mes a mes para los próximos 12 meses,
    partiendo del mes base (Mayo 2026). Integra datos historicos reales si
    estan disponibles en /data/processed.
    """
    log.info("Proyectando matriz 12 meses (mes base: %s %d)...", _nombre_mes(MES_BASE), ANIO_BASE)

    meses = []
    m, a = MES_BASE, ANIO_BASE
    for _ in range(12):
        meses.append((m, a))
        m += 1
        if m > 12:
            m = 1
            a += 1

    PROC_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
    so_hist_path = PROC_DIR / "sellout_historico_clean.csv"
    si_hist_path = PROC_DIR / "sellin_historico_clean.csv"

    def _load_hist(path):
        if not path.exists():
            return pd.DataFrame()
        df_h = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig")
        df_h.columns = df_h.columns.str.strip()
        # Normalizar columna año — puede llamarse 'año' o 'ano'
        for col in df_h.columns:
            if col.lower().startswith("a") and col.lower().endswith("o"):
                df_h.rename(columns={col: "_ano"}, inplace=True)
                break
        return df_h

    df_so_hist = _load_hist(so_hist_path)
    df_si_hist = _load_hist(si_hist_path)

    if not df_so_hist.empty:
        df_so_hist["sku"] = df_so_hist["sku"].astype(str).str.strip()
        df_so_hist["mes"] = df_so_hist["mes"].astype(str).str.strip().str.lower()
        df_so_hist["_ano"] = df_so_hist["_ano"].astype(str).str.strip()
        df_so_hist["unidades_sellout"] = pd.to_numeric(df_so_hist["unidades_sellout"], errors="coerce").fillna(0)

    if not df_si_hist.empty:
        df_si_hist["sku"] = df_si_hist["sku"].astype(str).str.strip()
        df_si_hist["mes"] = df_si_hist["mes"].astype(str).str.strip().str.lower()
        df_si_hist["_ano"] = df_si_hist["_ano"].astype(str).str.strip()
        df_si_hist["unidades_sellin"] = pd.to_numeric(df_si_hist["unidades_sellin"], errors="coerce").fillna(0)

    # Asegurar sku type
    df["sku"] = df["sku"].astype(str)

    for mes, anio in meses:
        estac      = ESTACIONALIDAD[mes]
        semanas    = SEMANAS_POR_MES[mes]
        lbl        = f"{_nombre_mes(mes)[:3].lower()}_{anio}"
        nombre_mes = _nombre_mes(mes).lower()

        # El año real del dato histórico:
        # Para todos los meses, la proyección de la API asume que los datos históricos
        # para rellenar la proyección son del año anterior (trailing 12 months).
        # Esto asegura que al proyectar Jul 2026 -> Jul 2027, Ene 2027 se llene con Ene 2026,
        # y Jul 2026 se llene con Jul 2025 (alineado con la vista del dashboard "Últimos 12 meses").
        anio_hist = anio - 1

        # Inicializamos en 0. Si no hay historia real para este mes, debe ser 0 
        # para no mostrar ventas falsas (proyecciones) en el pasado en el dashboard.
        col_so = f"sellout_{lbl}"
        df[col_so] = 0.0

        # Override con Sell-Out histórico real si existe para este mes/año
        if not df_so_hist.empty:
            hist_sub = df_so_hist[
                (df_so_hist["mes"] == nombre_mes) & (df_so_hist["_ano"] == str(anio_hist))
            ]
            if not hist_sub.empty:
                df = df.merge(hist_sub[["sku", "unidades_sellout"]], on="sku", how="left")
                mask = df["unidades_sellout"].notna()
                df.loc[mask, col_so] = df.loc[mask, "unidades_sellout"].round(0)
                df.drop(columns=["unidades_sellout"], inplace=True)
                log.info("Integrado Sell-Out historico real para %s (hist_ano=%d, %d SKUs)",
                         lbl, anio_hist, mask.sum())

        # Trigger de cierre
        trigger_ok = _trigger_update_ok(mes, anio, hoy)
        df[f"trigger_cerrado_{lbl}"] = trigger_ok

        # Inicializamos Sell-In en 0
        col_si = f"sellin_{lbl}"
        df[col_si] = 0.0

        # Override con Sell-In histórico real si existe para este mes/año
        if not df_si_hist.empty:
            hist_sub = df_si_hist[
                (df_si_hist["mes"] == nombre_mes) & (df_si_hist["_ano"] == str(anio_hist))
            ]
            if not hist_sub.empty:
                df = df.merge(hist_sub[["sku", "unidades_sellin"]], on="sku", how="left")
                mask = df["unidades_sellin"].notna()
                df.loc[mask, col_si] = df.loc[mask, "unidades_sellin"].round(0)
                df.drop(columns=["unidades_sellin"], inplace=True)
                log.info("Integrado Sell-In historico real para %s (%d SKUs)", lbl, mask.sum())

    log.info("Matriz 12 meses generada: %d columnas de proyeccion.", 12 * 2)
    return df, meses


# ──────────────────────────────────────────────────────────────────────────────
# Paso 4 — Inteligencia Comparativa: YoY y Picos
# ──────────────────────────────────────────────────────────────────────────────

def _calcular_yoy_y_picos(df: pd.DataFrame, meses: list) -> pd.DataFrame:
    """
    YoY (Year-over-Year):
      Compara el Sell-Out proyectado del mes actual (Mayo 2026) contra el
      mismo mes del año anterior. Como no tenemos datos de Mayo 2025 en las
      tablas, el YoY se calcula así:
        - Sell-Out_base (Mayo 2026) = ritmo_semanal × semanas_mayo × estac_mayo
        - Sell-Out_año_anterior = Sell-Out_base × (1 / factor_tendencia_catalogo)
          donde factor_tendencia = 1.08 (crecimiento del catálogo 8% YoY estimado)
        - yoy_pct = ((SO_2026 - SO_2025) / SO_2025) × 100

    Picos:
      mes_pico_sellout: nombre del mes con mayor Sell-Out en los 12 meses
      mes_pico_sellin:  nombre del mes con mayor Sell-In en los 12 meses
    """
    FACTOR_TENDENCIA_YOY = 1.08   # crecimiento estimado del negocio 8% anual

    log.info("Calculando YoY y meses pico...")

    # Columnas de sell-out y sell-in para los 12 meses
    cols_so = [f"sellout_{_nombre_mes(m)[:3].lower()}_{a}" for m, a in meses]
    cols_si = [f"sellin_{_nombre_mes(m)[:3].lower()}_{a}" for m, a in meses]
    labels  = [f"{_nombre_mes(m)} {a}" for m, a in meses]

    # YoY del mes base (Mayo 2026 vs Mayo 2025)
    col_so_base  = cols_so[0]   # primer mes = mes base (Mayo 2026)
    so_2026 = df[col_so_base]
    so_2025 = so_2026 / FACTOR_TENDENCIA_YOY   # estimación año anterior
    df["yoy_sellout_pct"] = ((so_2026 - so_2025) / so_2025.replace(0, float("nan")) * 100).round(2)
    df["sellout_mes_anterior_estimado"] = so_2025.round(0)

    # Mes pico Sell-Out: índice del máximo entre las 12 proyecciones
    so_matrix = df[cols_so].values
    idx_max_so = so_matrix.argmax(axis=1)
    df["mes_pico_sellout"]         = [labels[i] for i in idx_max_so]
    df["valor_pico_sellout_uds"]   = so_matrix.max(axis=1).round(0)

    # Mes pico Sell-In
    si_matrix  = df[cols_si].values
    idx_max_si = si_matrix.argmax(axis=1)
    df["mes_pico_sellin"]          = [labels[i] for i in idx_max_si]
    df["valor_pico_sellin_uds"]    = si_matrix.max(axis=1).round(0)

    log.info("YoY calculado. Crecimiento medio: %.1f%%", df["yoy_sellout_pct"].mean())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Paso 5 — Sell-In Ajustado por UMP
# ──────────────────────────────────────────────────────────────────────────────

def _integrar_stock_familia_en_sugerencia(df: pd.DataFrame, engine) -> pd.DataFrame:
    """Carga familias activas y aplica su stock consolidado al cálculo."""
    try:
        try:
            from src.services.maquila_service import (
                build_maquila_families,
                build_product_lookup_by_internal_code,
            )
            from src.services.purchase_stock_service import aplicar_stock_familia_para_sugerencia
        except ModuleNotFoundError:
            # Compatibilidad al ejecutar directamente: python src/planner.py
            from services.maquila_service import (
                build_maquila_families,
                build_product_lookup_by_internal_code,
            )
            from services.purchase_stock_service import aplicar_stock_familia_para_sugerencia

        lookup_dict = build_product_lookup_by_internal_code(
            df,
            ritmo_col="total_4_sem_verificado",
        )

        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)

        cantidad_skus = sum(
            1 for familia in familias_map.values()
            if len(familia.get("familia_skus") or []) > 1
        )
        log.info(
            "Stock de familia aplicado a la sugerencia de compra para %d SKU(s).",
            cantidad_skus,
        )
    except Exception as exc:
        log.warning(
            "No se pudieron cargar las familias de maquila para la sugerencia (%s). "
            "Se utilizará stock individual.",
            exc,
        )
        familias_map = {}

        try:
            from src.services.purchase_stock_service import aplicar_stock_familia_para_sugerencia
        except ModuleNotFoundError:
            from services.purchase_stock_service import aplicar_stock_familia_para_sugerencia

    return aplicar_stock_familia_para_sugerencia(df, familias_map)


def _ajustar_por_ump(df: pd.DataFrame, meses: list, engine) -> pd.DataFrame:
    """
    Para cada mes, calcula el Sell-In ajustado al múltiplo de UMP (gancheras).

    sellin_ajustado_mmm_aaaa = ceil(sellin_mmm_aaaa / ump) × ump

    También calcula la sugerencia de compra inmediata (próximo mes) ajustada.
    """
    log.info("Ajustando Sell-In por UMP (Unidad Mínima de Pedido)...")

    ump = df["ump"].fillna(0)
    ajustados = 0

    for mes, anio in meses:
        lbl     = f"{_nombre_mes(mes)[:3].lower()}_{anio}"
        col_si  = f"sellin_{lbl}"
        col_adj = f"sellin_ump_{lbl}"

        df[col_adj] = df.apply(
            lambda row, c=col_si: _ceil_to_multiple(
                float(row[c]) if not pd.isna(row[c]) else 0.0,
                float(row["ump"]) if not pd.isna(row["ump"]) and row["ump"] > 0 else 0.0
            ),
            axis=1
        )
        ajustados += 1

    # -------------------------------------------------------------------------
    # Nueva Sugerencia de Compra (Modelo de Cobertura Dinámica)
    # -------------------------------------------------------------------------
    log.info("Calculando Sugerencia de Compra con Target Dinámico...")
    
    # 1. Ritmo Pasado = promedio semanal * 4.33 (mes)
    df["sug_ritmo_pasado"] = df["ritmo_semanal_uds"] * 4.33
    
    # 2. Ritmo Futuro = promedio Sell-Out próximos 4 meses
    cols_so_prox_4 = [f"sellout_{_nombre_mes(m)[:3].lower()}_{a}" for m, a in meses[0:4]]
    # Asegurar que las columnas existen y sacar promedio
    exist_cols_so = [c for c in cols_so_prox_4 if c in df.columns]
    df["sug_ritmo_futuro"] = df[exist_cols_so].mean(axis=1) if exist_cols_so else 0.0
    
    # 3. Ritmo Consolidado = MAX(Pasado, Futuro)
    df["sug_ritmo_mensual"] = df[["sug_ritmo_pasado", "sug_ritmo_futuro"]].max(axis=1).round(0)
    
    # 4. Target de Stock Configurable
    try:
        with engine.connect() as conn:
            df_conf = pd.read_sql(text("SELECT tipo_regla, clave, meses FROM config_cobertura"), conn)
    except Exception as e:
        log.warning(f"No se pudo cargar config_cobertura ({e}), usando 5.0 por defecto.")
        df_conf = pd.DataFrame(columns=["tipo_regla", "clave", "meses"])
    
    dict_sku = df_conf[df_conf["tipo_regla"] == "SKU"].set_index("clave")["meses"].to_dict()
    dict_cat = df_conf[df_conf["tipo_regla"] == "CATEGORIA"].set_index("clave")["meses"].to_dict()
    global_val_row = df_conf[(df_conf["tipo_regla"] == "GLOBAL") & (df_conf["clave"] == "*")]
    global_val = float(global_val_row["meses"].iloc[0]) if not global_val_row.empty else 5.0

    def _resolver_cobertura(row):
        sku = str(row.get("sku", ""))
        cat = str(row.get("categoria", ""))
        if sku in dict_sku:
            return float(dict_sku[sku]), "SKU"
        if pd.notna(row.get("categoria")) and cat in dict_cat:
            return float(dict_cat[cat]), "CATEGORIA"
        if not global_val_row.empty:
            return global_val, "GLOBAL"
        return 5.0, "FALLBACK"

    res = df.apply(_resolver_cobertura, axis=1, result_type="expand")
    df["meses_cobertura_objetivo"] = res[0]
    df["origen_cobertura_objetivo"] = res[1]

    df["sug_target_meses"] = df["meses_cobertura_objetivo"]
    df["sug_target_uds"] = (df["sug_ritmo_mensual"] * df["sug_target_meses"]).round(0)
    df["stock_objetivo"] = df["sug_target_uds"]
    
    # 5. Inventario Disponible
    # Si el SKU pertenece a una familia de maquila activa, el stock físico útil
    # para decidir la compra es la suma de todos los integrantes de la familia.
    # El stock individual se conserva en stock_act para inventario y alertas.
    df = _integrar_stock_familia_en_sugerencia(df, engine)
    df["sug_cantidad_transito"] = df.get("sug_transito_actual", df.get("cantidad_transito", pd.Series(0, index=df.index))).fillna(0)
    inv_disponible = df["sug_stock_actual"] + df["sug_cantidad_transito"]
    
    # 6. Sugerencia Neta Bruta
    sug_bruta = df["sug_target_uds"] - inv_disponible
    sug_bruta = sug_bruta.clip(lower=0)
    df["sugerencia_bruta"] = sug_bruta
    
    # 7. Ajuste por UMP (U/E)
    df["sugerencia_compra_inmediata_uds"] = df.apply(
        lambda row: _ceil_to_multiple(sug_bruta[row.name], row["ump"]), axis=1
    ).round(0)
    df["sugerencia_final"] = df["sugerencia_compra_inmediata_uds"]

    log.info("UMP aplicado en %d meses. SKUs sin UMP (sin ajuste): %d",
             ajustados, (ump <= 0).sum())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Paso 6 — Excepciones y Alertas de Inventario
# ──────────────────────────────────────────────────────────────────────────────

def _calcular_excepciones_y_alertas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula reglas de negocio, excepciones y el semáforo final de alertas de inventario.
    Centraliza toda la lógica de validación del SKU.
    """
    from datetime import datetime, timedelta
    import json
    log.info("Calculando excepciones de negocio y alertas de inventario...")

    df["excepciones"] = "[]"
    df["requiere_revision"] = 0
    df["bloquea_compra_automatica"] = 0
    df["forecast_origen"] = "ALGORITMO"
    df["nivel_alerta"] = "VERDE"
    df["fecha_estimada_quiebre"] = None
    df["explicacion_compra"] = ""

    today = datetime.now()

    for idx, row in df.iterrows():
        excepciones = []
        requiere = False
        bloquea = False
        
        sku = str(row.get("sku", ""))
        stock = float(row.get("stock_act", 0) if pd.notna(row.get("stock_act")) else 0)
        ump = float(row.get("ump", 0) if pd.notna(row.get("ump")) else 0)
        ritmo = float(row.get("sug_ritmo_mensual", 0) if pd.notna(row.get("sug_ritmo_mensual")) else 0)
        estado = str(row.get("estado", "")).upper()
        transito = float(row.get("cantidad_transito", 0) if pd.notna(row.get("cantidad_transito")) else 0)
        eta_raw = row.get("eta_proxima")
        target_meses = float(row.get("meses_cobertura_objetivo", 5.0) if pd.notna(row.get("meses_cobertura_objetivo")) else 5.0)
        
        # 1. DATOS_INCOMPLETOS
        if not sku or sku == "nan" or pd.isna(row.get("nombre_producto")):
            excepciones.append("DATOS_INCOMPLETOS")
            requiere = True
            bloquea = True

        # 2. STOCK_NEGATIVO
        if stock < 0:
            excepciones.append("STOCK_NEGATIVO")
            requiere = True
            bloquea = True

        # 3. PRODUCTO_DESCONTINUADO
        if estado in ["DESCONTINUADO", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"]:
            excepciones.append("PRODUCTO_DESCONTINUADO")
            bloquea = True

        # 4. SIN_UMP
        if ump <= 0 and "PRODUCTO_DESCONTINUADO" not in excepciones:
            excepciones.append("SIN_UMP")
            requiere = True
            bloquea = True

        # 5. SIN_ETA_TRANSITO
        if transito > 0 and pd.isna(eta_raw):
            excepciones.append("SIN_ETA_TRANSITO")
            requiere = True

        # 6. SIN_VENTAS_SUFICIENTES
        total_4_sem = float(row.get("total_4_sem_verificado", 0) if pd.notna(row.get("total_4_sem_verificado")) else 0)
        if total_4_sem <= 0 and "PRODUCTO_DESCONTINUADO" not in excepciones:
            excepciones.append("SIN_VENTAS_SUFICIENTES")
            requiere = True

        # 7. PRODUCTO_NUEVO
        if estado == "NUEVO" or ("SIN_VENTAS_SUFICIENTES" in excepciones and stock > 0):
            if "PRODUCTO_NUEVO" not in excepciones:
                excepciones.append("PRODUCTO_NUEVO")
                requiere = True
        
        df.at[idx, "excepciones"] = json.dumps(excepciones)
        df.at[idx, "requiere_revision"] = int(requiere)
        df.at[idx, "bloquea_compra_automatica"] = int(bloquea)

        # Calculo de Semáforo
        dur_solo_stock = 999.0 if ritmo == 0 else stock / ritmo
        
        alerta = "VERDE"
        if dur_solo_stock > 10:
            alerta = "AZUL"
        elif dur_solo_stock < 4:
            alerta = "AMARILLO"
        if dur_solo_stock < 2.5:
            alerta = "NARANJA"
        if dur_solo_stock < 1.0:
            alerta = "ROJO"
            
        if transito > 0 and pd.notna(eta_raw):
            alerta = "MORADO"
            
        df.at[idx, "nivel_alerta"] = alerta
        
        # Bloqueo
        sugerencia_final = float(row.get("sugerencia_compra_inmediata_uds", 0))
        if bloquea:
            sugerencia_final = 0
            df.at[idx, "sugerencia_final"] = 0
            df.at[idx, "sugerencia_compra_inmediata_uds"] = 0

        # Calcular Fecha Estimada de Quiebre
        fecha_quiebre = today + timedelta(days=dur_solo_stock * 30.4) if dur_solo_stock < 999 else None
        df.at[idx, "fecha_estimada_quiebre"] = fecha_quiebre

        # Construir Explicacion
        explicacion = ""
        
        # Primero evaluamos overrides de forecast o bloqueos estructurales
        if "FORECAST_MANUAL" in excepciones:
            explicacion = "Forecast manual activo. La recomendación se calculó usando una proyección definida por usuario."
        elif "PRODUCTO_DESCONTINUADO" in excepciones:
            explicacion = "Producto descontinuado. Compra automática bloqueada."
        elif bloquea:
            explicacion = "Condición de error bloquea la recomendación automática de compra (revisar excepciones)."
        else:
            cob_actual = f"Cobertura actual: {dur_solo_stock:.1f} meses." if dur_solo_stock < 999 else "Cobertura actual: +10 meses."
            
            if transito > 0:
                if pd.isna(eta_raw):
                    explicacion = "Tránsito registrado sin ETA. La cobertura futura no puede validarse hasta confirmar fecha de llegada."
                else:
                    eta_dt = pd.to_datetime(eta_raw)
                    eta_str = eta_dt.strftime("%d %b") if pd.notna(eta_dt) else "desconocida"
                    if fecha_quiebre and eta_dt < fecha_quiebre:
                        explicacion = f"{cob_actual} Existe tránsito de {transito:g} unidades con ETA {eta_str}, antes de la fecha estimada de quiebre. No se recomienda compra adicional por ahora."
                    else:
                        if sugerencia_final > 0:
                            sug = f"Se sugieren {sugerencia_final:g} unidades (con ajuste UMP) para alcanzar target de {target_meses} meses."
                            explicacion = f"{cob_actual} Existe tránsito con ETA {eta_str}, pero no cubre el requerimiento a tiempo. {sug}"
                        else:
                            explicacion = f"{cob_actual} Existe tránsito con ETA {eta_str} y stock suficiente. No se requiere comprar."
            else:
                if sugerencia_final > 0:
                    semanas_quiebre = dur_solo_stock * 4.33
                    q_str = f"Quiebre estimado en {semanas_quiebre:.1f} semanas." if dur_solo_stock < 999 else "Quiebre estimado en +50 semanas."
                    sug = f"Se sugieren {sugerencia_final:g} unidades para alcanzar target de {target_meses} meses."
                    explicacion = f"{q_str} {cob_actual} No existe tránsito confirmado. {sug}"
                else:
                    explicacion = f"{cob_actual} No hay necesidad inminente de reposición para el target de {target_meses} meses."

        df.at[idx, "explicacion_compra"] = explicacion

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Paso 7 — Persistencia
# ──────────────────────────────────────────────────────────────────────────────

def _persistir(df: pd.DataFrame, engine) -> int:
    """
    Sobreescribe la tabla planificacion_sop en PostgreSQL (if_exists='replace').
    Sanitiza nombres de columna y convierte tipos problemáticos.
    """
    log.info("Persistiendo planificacion_sop en PostgreSQL (%d filas x %d cols)...",
             *df.shape)

    # Sanitizar nombres de columna
    df = df.copy()
    df.columns = (
        df.columns
        .str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^a-z0-9_]", "", regex=True)
        .str.strip("_")
    )

    # Eliminar columnas de trigger (internas, no van a la BD)
    trigger_cols = [c for c in df.columns if c.startswith("trigger_cerrado_")]
    df = df.drop(columns=trigger_cols)

    # Convertir booleanos y tipos nullable
    for col in df.select_dtypes(include=["bool"]).columns:
        df[col] = df[col].astype(int)
    for col in df.select_dtypes(include=["Int64"]).columns:
        df[col] = df[col].astype("float64")

    try:
        df.to_sql(
            name      = TABLA_PLAN,
            con       = engine,
            if_exists = "replace",
            index     = False,
            chunksize = CHUNK_SIZE,
            method    = "multi",
        )
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Error persistiendo {TABLA_PLAN}: {exc}") from exc

    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {TABLA_PLAN}")).scalar()

    log.info("planificacion_sop guardada: %d filas en PostgreSQL.", count)
    return count


# ──────────────────────────────────────────────────────────────────────────────
# Función principal exportada
# ──────────────────────────────────────────────────────────────────────────────

def run_planning(archivos_proc=None) -> dict:
    """
    Ejecuta el Módulo de Inteligencia SOP completo.

    Returns:
        dict con métricas de resultado: filas, columnas, tabla destino
    """
    hoy = date.today()

    log.info("=" * 60)
    log.info("FASE 4 - Modulo de Inteligencia SOP iniciado")
    log.info("Fecha de ejecucion: %s | Mes base: %s %d",
             hoy.isoformat(), _nombre_mes(MES_BASE), ANIO_BASE)
    log.info("=" * 60)

    engine = _build_engine()

    # Paso 1: Extracción y cruce
    log.info("--- [4.1] Extraccion y cruce ---")
    df = _extraer_datos(engine)

    # Paso 2: Base transaccional
    log.info("--- [4.2] Base transaccional 4 semanas ---")
    df = _calcular_base_transaccional(df)

    # Paso 3: Proyección 12 meses
    log.info("--- [4.3] Proyeccion matricial 12 meses ---")
    df, meses = _proyectar_12_meses(df, hoy)

    # Paso 4: YoY y picos
    log.info("--- [4.4] Inteligencia comparativa YoY y picos ---")
    df = _calcular_yoy_y_picos(df, meses)

    # Paso 5: Ajuste UMP
    log.info("--- [4.5] Sell-In ajustado por UMP ---")
    df = _ajustar_por_ump(df, meses, engine)

    # Paso 6: Excepciones y Alertas
    log.info("--- [4.6] Excepciones y Alertas de Inventario ---")
    df = _calcular_excepciones_y_alertas(df)

    # --- INTEGRACION DINAMICA ---
    if os.getenv("DYNAMIC_PLANNER_ENABLED", "true").lower() == "true":
        log.info("--- [4.6.1] Integrando Planificacion Dinamica en Shadow Mode ---")
        try:
            import sys
            from pathlib import Path
            base = str(Path(__file__).resolve().parent.parent)
            if base not in sys.path:
                sys.path.insert(0, base)
            from src.dynamic_planner import run_dynamic_pipeline
            df_din = run_dynamic_pipeline()
            if not df_din.empty:
                # Mapeo Legacy
                df["sugerencia_compra_legacy"] = df["sugerencia_compra_inmediata_uds"]
                df["explicacion_compra_legacy"] = df["explicacion_compra"]
                
                # Merge
                df_din["sku"] = df_din["sku"].astype(str)
                df["sku"] = df["sku"].astype(str)
                df = df.merge(df_din, on="sku", how="left")
                
                # Comparaciones
                def compare_logic(row):
                    leg = row.get("sugerencia_compra_legacy", 0)
                    din = row.get("sugerencia_compra_dinamica", 0)
                    if pd.isna(leg): leg = 0
                    if pd.isna(din): return "No comparable por falta de datos"
                    
                    if leg == 0 and din == 0:
                        return "Ambas recomiendan no comprar"
                    if leg == 0 and din > 0:
                        return "Dinamica compra / Legacy no compra"
                    if leg > 0 and din == 0:
                        return "Legacy compra / Dinamica no compra"
                    
                    diff = abs(din - leg)
                    diff_pct = (diff / leg) if leg > 0 else 0
                    if diff_pct > 0.2:
                        return "Ambas compran con diferencia superior al 20%"
                    return "Ambas recomiendan comprar"
                    
                df["diferencia_compra_dinamica_legacy"] = df["sugerencia_compra_dinamica"] - df["sugerencia_compra_legacy"]
                df["diferencia_porcentual_dinamica_legacy"] = np.where(
                    df["sugerencia_compra_legacy"] > 0,
                    df["diferencia_compra_dinamica_legacy"] / df["sugerencia_compra_legacy"],
                    np.nan
                )
                df["recomendacion_coincide"] = df.apply(compare_logic, axis=1)
                
                log.info(f"Integracion Dinamica completada. {len(df_din)} SKUs cruzados.")
        except Exception as e:
            log.error(f"Error integrando pipeline dinamico: {e}")

    # Paso 7: Persistencia
    log.info("--- [4.7] Persistencia en PostgreSQL ---")
    count = _persistir(df, engine)

    # Reporte de verificación
    log.info("=" * 60)
    log.info("VERIFICACION PLANIFICACION_SOP:")
    with engine.connect() as conn:
        # Muestra de validación: SKU, stock, ritmo, pico, yoy, sugerencia_compra
        rows = conn.execute(text("""
            SELECT
                sku,
                nombre_producto,
                stock_act,
                ritmo_semanal_uds,
                total_4_sem_verificado,
                yoy_sellout_pct,
                mes_pico_sellout,
                mes_pico_sellin,
                sugerencia_compra_inmediata_uds,
                ump
            FROM planificacion_sop
            ORDER BY total_4_sem_verificado DESC
            LIMIT 8
        """)).mappings().fetchall()

        log.info("  %-10s %-28s %7s %8s %7s %6s  %-15s  %8s  %5s",
                 "SKU", "Producto", "Stock", "Ritmo/sem", "4-Sem", "YoY%",
                 "Pico SellOut", "Sug.Compra", "UMP")
        log.info("  " + "-" * 110)
        for r in rows:
            log.info("  %-10s %-28s %7.0f %8.1f %7.0f %6.1f  %-15s  %8.0f  %5s",
                     r["sku"] or "",
                     (r["nombre_producto"] or "")[:28],
                     r["stock_act"] or 0,
                     r["ritmo_semanal_uds"] or 0,
                     r["total_4_sem_verificado"] or 0,
                     r["yoy_sellout_pct"] or 0,
                     (r["mes_pico_sellout"] or "")[:15],
                     r["sugerencia_compra_inmediata_uds"] or 0,
                     r["ump"] or "N/A")
    log.info("=" * 60)

    engine.dispose()
    return {
        "tabla"   : TABLA_PLAN,
        "filas"   : count,
        "columnas": len(df.columns),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada standalone
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        resultado = run_planning()
        print(f"\nPlanificacion SOP generada:")
        print(f"  Tabla:    {resultado['tabla']}")
        print(f"  Filas:    {resultado['filas']}")
        print(f"  Columnas: {resultado['columnas']}")
        sys.exit(0)
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)
