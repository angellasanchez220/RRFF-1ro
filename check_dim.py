from sqlalchemy import text
from api.db import engine
with engine.connect() as conn:
    print(conn.execute(text("SELECT sku, condicion FROM dim_productos WHERE sku LIKE '%7064098%'")).fetchall())
