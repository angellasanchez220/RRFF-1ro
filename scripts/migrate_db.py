import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.db import engine
from sqlalchemy import text

def run_migration():
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE receta_maquila_componentes ADD COLUMN no_transformable BOOLEAN DEFAULT FALSE"))
            print("Columna no_transformable agregada correctamente.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("La columna ya existe.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    run_migration()
