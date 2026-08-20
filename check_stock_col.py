from api.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT column_name, data_type, column_default, is_nullable
        FROM information_schema.columns
        WHERE table_name='dim_productos'
        ORDER BY ordinal_position
    """))
    cols = r.fetchall()
    print("Columnas de dim_productos:")
    for c in cols:
        print(f"  {c[0]:30s} {c[1]:20s} default={c[2]}  nullable={c[3]}")
