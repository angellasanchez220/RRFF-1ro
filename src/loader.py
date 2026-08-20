"""
loader.py — Módulo de Carga RRFF Soft
=======================================
Fase 3 del orquestador: lee los DataFrames procesados desde /data/processed
y los inyecta en las tablas PostgreSQL de la base de datos RRFF_AS_db.

Tablas de destino:
  dim_productos   ←  maestro_consolidado.csv   (if_exists='replace')
  fact_ventas     ←  ventas_semanales_clean.csv (if_exists='replace')
  fact_transito   ←  transito_clean.csv         (if_exists='replace')

Estrategia de carga:
  - 'replace': DROP + CREATE + INSERT en cada ejecución.
    Garantiza que siempre tengamos la fotografía más reciente.
  - Tipado explícito: SQLAlchemy mapea los dtypes de Pandas a tipos PG correctos.
  - Chunking: inserciones en lotes de 500 filas para no saturar el buffer.
  - Transacción atómica: si falla cualquier tabla, se hace rollback de esa tabla.

Dependencias: sqlalchemy, psycopg2-binary, pandas, python-dotenv
"""

import logging
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# ──────────────────────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).resolve().parent.parent
PROC_DIR  = BASE_DIR / "data" / "processed"

# ──────────────────────────────────────────────────────────────────────────────
# Configuración de tablas
# ──────────────────────────────────────────────────────────────────────────────

TABLA_DIM_PRODUCTOS = "dim_productos"
TABLA_FACT_VENTAS   = "fact_ventas"
TABLA_FACT_TRANSITO = "fact_transito"
CHUNK_SIZE          = 500   # filas por lote de inserción

# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LOADER] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("loader")


# ──────────────────────────────────────────────────────────────────────────────
# Conexión
# ──────────────────────────────────────────────────────────────────────────────

def _build_engine():
    """
    Construye el engine de SQLAlchemy leyendo las credenciales desde .env.
    Variables requeridas: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS.
    """
    load_dotenv()

    # Render y nube: DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        engine = create_engine(
            db_url,
            connect_args={"connect_timeout": 10},
            pool_pre_ping=True,
        )
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            log.info("Conexion establecida via DATABASE_URL: %s", version[:65])
        return engine

    host = os.getenv("DB_HOST", "localhost").strip().strip('"')
    port = os.getenv("DB_PORT", "5432").strip().strip('"')
    name = os.getenv("DB_NAME", "").strip().strip('"')
    user = os.getenv("DB_USER", "postgres").strip().strip('"')
    pwd  = os.getenv("DB_PASS", "").strip().strip('"')

    if not name:
        raise EnvironmentError("DB_NAME no definido en el archivo .env")

    log.info("Conectando a PostgreSQL: %s@%s:%s/%s", user, host, port, name)

    conn_str = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
    engine = create_engine(
        conn_str,
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,   # verifica la conexión antes de usarla
    )

    # Probar conexión inmediatamente
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        log.info("Conexion establecida: %s", version[:65])

    return engine


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de carga
# ──────────────────────────────────────────────────────────────────────────────

def _read_processed_csv(filename: str) -> pd.DataFrame:
    """Lee un CSV de /data/processed con los parámetros estándar del pipeline."""
    path = PROC_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Archivo no encontrado en /data/processed: {filename}. "
            f"Asegúrate de que la Fase 2 completó exitosamente."
        )
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    log.info("Leido: %s  (%d filas x %d cols)", filename, *df.shape)
    return df


def _load_table(
    df: pd.DataFrame,
    tabla: str,
    engine,
    if_exists: str = "replace",
) -> int:
    """
    Carga un DataFrame en una tabla PostgreSQL.

    Args:
        df       : DataFrame a cargar
        tabla    : nombre de la tabla destino
        engine   : engine de SQLAlchemy
        if_exists: 'replace' (drop+create+insert) o 'append'

    Returns:
        Número de filas insertadas confirmadas por COUNT(*) en PG.
    """
    log.info(
        "Cargando tabla '%s'  [%d filas | if_exists='%s' | chunk=%d]",
        tabla, len(df), if_exists, CHUNK_SIZE
    )

    # Sanitizar nombres de columna para PostgreSQL
    # (minúsculas, sin espacios — ya procesado en Fase 2, pero garantizamos)
    df = df.copy()
    df.columns = (
        df.columns
        .str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^a-z0-9_]", "", regex=True)
        .str.strip("_")
    )

    # Tipos problemáticos: Int64 nullable de Pandas → INTEGER en PG
    for col in df.select_dtypes(include=["Int64", "Int32"]).columns:
        df[col] = df[col].astype("float64")   # psycopg2 no entiende Int64 nullable

    try:
        df.to_sql(
            name      = tabla,
            con       = engine,
            if_exists = if_exists,
            index     = False,
            chunksize = CHUNK_SIZE,
            method    = "multi",    # inserta múltiples filas por sentencia VALUES
        )
        log.info("  to_sql() completado.")

        # Añadir UNIQUE si es dim_productos y se reemplazó (para soportar ON CONFLICT)
        if tabla == "dim_productos" and if_exists == "replace":
            with engine.begin() as conn:
                try:
                    conn.execute(text("ALTER TABLE dim_productos ADD CONSTRAINT dim_productos_sku_key UNIQUE (sku);"))
                    log.info("  Restricción UNIQUE añadida a dim_productos(sku).")
                except Exception as e:
                    log.warning("  No se pudo añadir restricción UNIQUE a dim_productos: %s", e)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Error al cargar tabla '{tabla}': {exc}") from exc

    # Verificar conteo real en PostgreSQL
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()

    log.info(
        "  Confirmado en BD: %d filas en tabla '%s'", count, tabla
    )
    return count


def _verify_tables(engine, tablas: list[str]) -> None:
    """Imprime un resumen de las tablas cargadas: nombre, filas, columnas."""
    inspector = inspect(engine)
    log.info("=" * 60)
    log.info("VERIFICACION FINAL EN POSTGRESQL:")
    with engine.connect() as conn:
        for tabla in tablas:
            existe = inspector.has_table(tabla)
            if not existe:
                log.warning("  TABLA '%s': NO EXISTE", tabla)
                continue
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            cols  = [c["name"] for c in inspector.get_columns(tabla)]
            log.info(
                "  TABLA '%-20s': %d filas | %d columnas | cols=%s",
                tabla, count, len(cols), cols[:5]
            )
    log.info("=" * 60)



# ──────────────────────────────────────────────────────────────────────────────
# UPSERT dim_productos — preserva stock_act, condicion y ump
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_dim_productos(df: pd.DataFrame, engine) -> int:
    """
    Carga dim_productos usando INSERT ... ON CONFLICT (sku) DO UPDATE.
    - Nunca sobreescribe stock_act (lo preserva siempre).
    - Actualiza solo columnas de catálogo: nombre_producto, categoria,
      subcategoria, formato, estado, departamento, familia, etc.
    - Si el SKU no existe → INSERT con stock_act = 0.
    - Garantiza que la columna stock_act exista con default 0.
    """
    df = df.copy()
    # Normalizar columnas
    df.columns = (
        df.columns
        .str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^a-z0-9_]", "", regex=True)
        .str.strip("_")
    )

    # Columnas de catálogo que sí actualizamos desde el CSV
    CATALOG_COLS = [
        "nombre_producto", "codigo_femaco", "categoria", "subcategoria",
        "formato", "estado", "departamento", "familia", "subfamilia",
        "grupo", "conjunto", "gancheras",
    ]

    if "sku" not in df.columns:
        raise ValueError("El maestro_consolidado.csv no tiene columna 'sku'")

    df["sku"] = df["sku"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df = df[df["sku"].notna() & (df["sku"] != "") & (df["sku"] != "nan")].copy()

    with engine.begin() as conn:
        # Asegurar que la tabla existe con stock_act
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
        conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS stock_act FLOAT DEFAULT 0"))
        conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS condicion TEXT"))
        conn.execute(text("ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS ump FLOAT"))
        # Poner 0 donde stock_act es NULL
        conn.execute(text("UPDATE dim_productos SET stock_act = 0 WHERE stock_act IS NULL"))

        inserted = updated = 0
        for _, row in df.iterrows():
            sku = row["sku"]
            vals = {"sku": sku}
            for col in CATALOG_COLS:
                vals[col] = row[col] if col in df.columns and pd.notna(row.get(col)) else None

            # Construir SET dinámico solo con columnas que existen
            set_parts = ", ".join(
                f"{col} = EXCLUDED.{col}" for col in CATALOG_COLS if col in df.columns
            )

            sql = f"""
                INSERT INTO dim_productos (sku, {', '.join(c for c in CATALOG_COLS if c in df.columns)}, stock_act)
                VALUES (:sku, {', '.join(':' + c for c in CATALOG_COLS if c in df.columns)}, 0)
                ON CONFLICT (sku) DO UPDATE SET {set_parts}
                RETURNING (xmax = 0) AS was_inserted
            """
            r = conn.execute(text(sql), vals).fetchone()
            if r and r[0]:
                inserted += 1
            else:
                updated += 1

    count = inserted + updated
    log.info("  dim_productos UPSERT: %d insertados, %d actualizados (total: %d)", inserted, updated, count)
    return count


# ──────────────────────────────────────────────────────────────────────────────
# Función principal exportada
# ──────────────────────────────────────────────────────────────────────────────

def run_loading(archivos_proc: dict[str, Path] | None = None) -> dict[str, int]:
    """
    Ejecuta la Fase 3 completa: conecta a PostgreSQL e inyecta los datos
    procesados en las tablas dimensionales y de hechos.

    Args:
        archivos_proc: dict opcional {nombre_csv: Path} retornado por
                       run_transformation(). Se usa solo para logging.
                       Si es None, busca directamente en /data/processed.

    Returns:
        dict {nombre_tabla: filas_insertadas}
    """
    log.info("=" * 60)
    log.info("FASE 3 - Modulo de Carga iniciado")
    log.info("Fuente: %s", PROC_DIR)
    log.info("Destino: PostgreSQL (RRFF_AS_db)")
    log.info("=" * 60)

    # ── Conexión ──────────────────────────────────────────────────────────────
    try:
        engine = _build_engine()
    except Exception as exc:
        log.error("No se pudo conectar a PostgreSQL: %s", exc)
        raise

    resultados: dict[str, int] = {}

    # ── dim_productos ← maestro_consolidado.csv ───────────────────────────────
    # ESTRATEGIA: UPSERT por SKU — preserva stock_act, condicion y ump
    # que el usuario carga manualmente. NO usar replace (destruiria el stock).
    log.info("--- Cargando: dim_productos (UPSERT) ---")
    try:
        df_maestro = _read_processed_csv("maestro_consolidado.csv")
        count = _upsert_dim_productos(df_maestro, engine)
        resultados[TABLA_DIM_PRODUCTOS] = count
    except Exception as exc:
        log.error("Error cargando dim_productos: %s", exc)
        resultados[TABLA_DIM_PRODUCTOS] = -1

    # ── stock_act ← inventario_stock_clean.csv ────────────────────────────────
    # Carga el stock real de Femaco extraído de la matrix al campo stock_act.
    # Este paso era el que faltaba y dejaba stock_act en NULL.
    log.info("--- Cargando: stock_act desde inventario_stock_clean.csv ---")
    inv_path = PROC_DIR / "inventario_stock_clean.csv"
    if inv_path.exists():
        try:
            df_inv = _read_processed_csv("inventario_stock_clean.csv")
            df_inv.columns = df_inv.columns.str.lower().str.strip()
            stk_col = next((c for c in df_inv.columns if "stock" in c), None)
            if "sku" in df_inv.columns and stk_col:
                df_inv["sku"] = (
                    df_inv["sku"].astype(str).str.strip()
                    .str.replace(r"\.0$", "", regex=True)
                )
                df_inv[stk_col] = pd.to_numeric(df_inv[stk_col], errors="coerce").fillna(0)
                df_inv = df_inv[
                    df_inv["sku"].notna() & (df_inv["sku"] != "") & (df_inv["sku"] != "nan")
                ]
                updated_inv = 0
                with engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS stock_act FLOAT DEFAULT 0"
                    ))
                    conn.execute(text(
                        "UPDATE dim_productos SET stock_act = 0 WHERE stock_act IS NULL"
                    ))
                    for _, row in df_inv.iterrows():
                        r = conn.execute(
                            text("UPDATE dim_productos SET stock_act=:s WHERE sku=:u RETURNING sku"),
                            {"s": float(row[stk_col]), "u": row["sku"]}
                        )
                        if r.fetchone():
                            updated_inv += 1
                log.info("  stock_act desde matrix: %d SKUs actualizados", updated_inv)
            else:
                log.warning("  inventario_stock_clean.csv no tiene columnas sku/stock esperadas")
        except Exception as exc:
            log.error("Error cargando stock desde inventario_stock_clean.csv: %s", exc)
    else:
        log.warning("inventario_stock_clean.csv no encontrado — stock_act no se actualiza desde matrix.")

    # ── fact_ventas ← ventas_semanales_clean.csv ──────────────────────────────
    log.info("--- Cargando: fact_ventas ---")
    try:
        df_ventas = _read_processed_csv("ventas_semanales_clean.csv")
        count = _load_table(df_ventas, TABLA_FACT_VENTAS, engine, if_exists="replace")
        resultados[TABLA_FACT_VENTAS] = count
    except Exception as exc:
        log.error("Error cargando fact_ventas: %s", exc)
        resultados[TABLA_FACT_VENTAS] = -1

    # ── fact_transito ← transito_clean.csv ───────────────────────────────────
    log.info("--- Cargando: fact_transito ---")
    transito_path = PROC_DIR / "transito_clean.csv"
    if transito_path.exists():
        try:
            df_transito = _read_processed_csv("transito_clean.csv")
            for col_fecha in ["fecha_eta", "fecha_disponibilidad_real"]:
                if col_fecha in df_transito.columns:
                    df_transito[col_fecha] = df_transito[col_fecha].astype(str)
            count = _load_table(df_transito, TABLA_FACT_TRANSITO, engine, if_exists="replace")
            resultados[TABLA_FACT_TRANSITO] = count
        except Exception as exc:
            log.error("Error cargando fact_transito: %s", exc)
            resultados[TABLA_FACT_TRANSITO] = -1
    else:
        log.warning("transito_clean.csv no encontrado — fact_transito no se carga.")
        resultados[TABLA_FACT_TRANSITO] = 0

    # ── Verificación final ────────────────────────────────────────────────────
    _verify_tables(engine, [TABLA_DIM_PRODUCTOS, TABLA_FACT_VENTAS, TABLA_FACT_TRANSITO])

    # ── Resumen ───────────────────────────────────────────────────────────────
    log.info("RESUMEN DE CARGA:")
    for tabla, filas in resultados.items():
        if filas >= 0:
            log.info("  OK     %-20s  %d filas en PostgreSQL", tabla, filas)
        else:
            log.warning("  FALLO  %s", tabla)

    fallidos = [t for t, f in resultados.items() if f < 0]
    if fallidos:
        raise RuntimeError(
            f"Las siguientes tablas no pudieron cargarse: {fallidos}"
        )

    return resultados


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada standalone
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        tablas = run_loading()
        print("\nCarga completada:")
        for tabla, filas in tablas.items():
            print(f"  - {tabla}: {filas} filas en PostgreSQL")
        sys.exit(0)
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)
