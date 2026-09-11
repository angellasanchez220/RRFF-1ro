import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.db import engine
from sqlalchemy import text

def check():
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT id, sku_maquilable, descripcion FROM recetas_maquila WHERE sku_maquilable NOT LIKE 'FAM-%'"), conn)
        print(f"Existen {len(df)} recetas legacy. Ejemplos:")
        print(df.head())

if __name__ == "__main__":
    check()
