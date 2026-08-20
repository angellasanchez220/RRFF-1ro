from api.db import engine
from sqlalchemy import text
import pandas as pd

# Verificar columnas de fact_ventas
with engine.connect() as conn:
    cols = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='fact_ventas' ORDER BY ordinal_position LIMIT 30"
    )).fetchall()
    print("fact_ventas cols:", [r[0] for r in cols])

    # Buscar SKU CINTA ANTIDES en fact_ventas
    row = conn.execute(text(
        "SELECT * FROM fact_ventas WHERE sku='7064098' LIMIT 3"
    )).fetchall()
    if row:
        for r in row:
            print("fact_ventas row:", dict(r._mapping))
    else:
        # Mostrar muestra de fact_ventas
        r2 = conn.execute(text("SELECT * FROM fact_ventas LIMIT 2")).fetchall()
        for r in r2:
            print("fact_ventas sample:", dict(r._mapping))

# Verificar planificacion_sop para sem1
with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT sku, nombre_producto, sem1_uds, sem2_uds, sem3_uds, sem4_uds, sem_actual_uds, total_4_sem_uds, total_4_sem_verificado "
        "FROM planificacion_sop WHERE sem1_uds > 0 LIMIT 5"
    )).fetchall()
    if r:
        print("\nProductos CON sem1 > 0:")
        for row in r:
            print(dict(row._mapping))
    else:
        print("\nNINGUN producto tiene sem1_uds > 0 — bug confirmado en planner")
        r2 = conn.execute(text(
            "SELECT COUNT(*) as total, SUM(CASE WHEN sem1_uds > 0 THEN 1 ELSE 0 END) as con_sem1 "
            "FROM planificacion_sop"
        )).fetchone()
        print(f"Total SKUs: {r2.total} | Con sem1>0: {r2.con_sem1}")
