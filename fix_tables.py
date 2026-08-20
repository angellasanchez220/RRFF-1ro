import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load env
load_dotenv(Path(__file__).resolve().parent / ".env")
host = os.getenv("DB_HOST", "localhost").strip().strip('"')
port = os.getenv("DB_PORT", "5432").strip().strip('"')
name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
user = os.getenv("DB_USER", "postgres").strip().strip('"')
pwd  = os.getenv("DB_PASS", "postgres").strip().strip('"')
engine = create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}", isolation_level="AUTOCOMMIT")

with engine.connect() as conn:
    print("Eliminando duplicados en dim_productos (si los hay)...")
    try:
        conn.execute(text("""
            DELETE FROM dim_productos a USING (
                SELECT MIN(ctid) as ctid, sku
                FROM dim_productos 
                GROUP BY sku HAVING COUNT(*) > 1
            ) b
            WHERE a.sku = b.sku 
            AND a.ctid <> b.ctid
        """))
    except Exception as e:
        print("Aviso al eliminar duplicados:", e)

    print("Agregando restricción UNIQUE a dim_productos(sku)...")
    try:
        conn.execute(text("ALTER TABLE dim_productos ADD CONSTRAINT dim_productos_sku_key UNIQUE (sku);"))
        print("Restricción UNIQUE añadida.")
    except Exception as e:
        print("Aviso o error añadiendo UNIQUE:", e)
        
    print("Truncando fact_ventas (sellin y sellout)...")
    try:
        conn.execute(text("TRUNCATE TABLE fact_ventas CASCADE;"))
        print("fact_ventas truncada.")
    except Exception as e:
        print("Aviso o error truncando fact_ventas:", e)
        
    # Revisar si hay otras tablas que contengan la palabra sell
    try:
        res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [r[0] for r in res.fetchall()]
        for t in tables:
            if 'sell' in t.lower() and t != 'fact_ventas':
                print(f"Truncando {t}...")
                conn.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                print(f"{t} truncada.")
    except Exception as e:
        print(e)
            
print("Finalizado.")
