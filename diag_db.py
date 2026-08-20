"""
diag_db.py — Diagnostico completo del estado de la BD
"""
from api.db import engine
from sqlalchemy import text
import pandas as pd

with engine.connect() as conn:
    print("=" * 60)
    print("DIAGNOSTICO DE TABLAS")
    print("=" * 60)

    # Contar filas en cada tabla clave
    tablas = [
        "dim_productos",
        "fact_ventas",
        "planificacion_sop",
        "control_embarques",
    ]
    for t in tablas:
        try:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:30s}: {n} filas")
        except Exception as e:
            print(f"  {t:30s}: ERROR - {e}")

    print()
    print("=" * 60)
    print("COLUMNAS DE dim_productos")
    print("=" * 60)
    r = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='dim_productos'
        ORDER BY ordinal_position
    """))
    for row in r.fetchall():
        print(f"  {row[0]:30s} {row[1]}")

    print()
    print("=" * 60)
    print("MUESTRA dim_productos (primeras 5 filas)")
    print("=" * 60)
    df = pd.read_sql(text("SELECT sku, codigo_femaco, stock_act, nombre_producto FROM dim_productos LIMIT 5"), conn)
    print(df.to_string())

    print()
    print("=" * 60)
    print("stock_act en dim_productos")
    print("=" * 60)
    r2 = conn.execute(text("""
        SELECT
          COUNT(*) as total,
          COUNT(stock_act) as con_stock,
          COUNT(*) FILTER (WHERE stock_act IS NULL) as nullos,
          COUNT(*) FILTER (WHERE stock_act = 0) as en_cero,
          COUNT(*) FILTER (WHERE stock_act > 0) as con_valor
        FROM dim_productos
    """))
    row = r2.fetchone()
    print(f"  Total: {row[0]}, con stock: {row[1]}, NULL: {row[2]}, en cero: {row[3]}, con valor: {row[4]}")

    print()
    print("=" * 60)
    print("COLUMNAS DE fact_ventas (primeras 3 filas)")
    print("=" * 60)
    try:
        df2 = pd.read_sql(text("SELECT * FROM fact_ventas LIMIT 3"), conn)
        print("Columnas:", list(df2.columns))
        print(df2.head(3).to_string())
    except Exception as e:
        print(f"  ERROR: {e}")

    print()
    print("=" * 60)
    print("COLUMNAS planificacion_sop (muestra)")
    print("=" * 60)
    try:
        df3 = pd.read_sql(text("""
            SELECT sku, stock_act, sellout_may_2026, sellin_may_2026,
                   sellout_ene_2027, sellin_ene_2027
            FROM planificacion_sop LIMIT 3
        """), conn)
        print(df3.to_string())
    except Exception as e:
        print(f"  ERROR: {e}")

    print()
    print("=" * 60)
    print("ARCHIVOS PROCESADOS disponibles")
    print("=" * 60)

import os
from pathlib import Path
proc = Path("data/processed")
if proc.exists():
    for f in sorted(proc.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:40s} {size:8d} bytes")
else:
    print("  directorio data/processed NO existe")
