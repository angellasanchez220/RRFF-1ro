from api.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    cols = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='planificacion_sop' ORDER BY ordinal_position"
    )).fetchall()
    print("COLS planificacion_sop:")
    for r in cols:
        print(" ", r[0])

    row = conn.execute(text(
        "SELECT * FROM planificacion_sop LIMIT 1"
    )).fetchone()
    if row:
        print("\nSAMPLE ROW KEYS:", list(row._mapping.keys()))
        for k, v in row._mapping.items():
            if v not in (None, 0, 0.0, ''):
                print(f"  {k} = {v}")
