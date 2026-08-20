from api.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    cols = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='planificacion_sop' AND column_name LIKE 'sell%' "
        "ORDER BY ordinal_position"
    )).fetchall()
    print("Columnas sell* en planificacion_sop:")
    for c in cols:
        print(" ", c[0])

    # Muestra de datos para un SKU
    row = conn.execute(text(
        "SELECT * FROM planificacion_sop WHERE sku='7064098' LIMIT 1"
    )).fetchone()
    if row:
        mapping = dict(row._mapping)
        sell_data = {k: v for k, v in mapping.items() if 'sell' in k.lower()}
        print("\nDatos sell* para SKU 7064098:")
        for k, v in sell_data.items():
            print(f"  {k} = {v}")
