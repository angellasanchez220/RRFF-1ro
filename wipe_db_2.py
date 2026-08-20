import os
from sqlalchemy import text
from api.db import engine

def wipe_data():
    with engine.begin() as conn:
        print("Borrando datos ficticios adicionales...")
        conn.execute(text("TRUNCATE TABLE fact_ventas CASCADE;"))
        conn.execute(text("TRUNCATE TABLE fact_transito CASCADE;"))
        print("Datos borrados con éxito.")

if __name__ == "__main__":
    wipe_data()
