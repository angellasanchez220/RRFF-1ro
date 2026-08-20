import os
from sqlalchemy import text
from api.db import engine

def wipe_data():
    with engine.begin() as conn:
        print("Borrando datos ficticios...")
        conn.execute(text("TRUNCATE TABLE dim_productos CASCADE;"))
        conn.execute(text("TRUNCATE TABLE planificacion_sop CASCADE;"))
        conn.execute(text("TRUNCATE TABLE control_embarques CASCADE;"))
        conn.execute(text("TRUNCATE TABLE sku_observaciones CASCADE;"))
        # No truncar la tabla usuarios para que no pierda su acceso
        print("Datos borrados con éxito.")

if __name__ == "__main__":
    wipe_data()
