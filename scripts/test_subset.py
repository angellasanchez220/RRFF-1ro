import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.db import engine
from sqlalchemy import text
from src.services.maquila_service import build_maquila_families

def test_subset():
    with engine.connect() as conn:
        df_sop = pd.read_sql(text("SELECT sku, nombre_producto, stock_act, total_4_sem_verificado as ritmo_mensual FROM planificacion_sop"), conn)
        df_sop['sku'] = df_sop['sku'].astype(str)
        lookup = df_sop.set_index("sku").to_dict("index")
        
        familias_map = build_maquila_families(conn, lookup)
        
        all_passed = True
        for sku, data in familias_map.items():
            fam_skus = set(x['sku'] for x in data['familia_skus'])
            reemplazos = set(x['sku'] for x in data['reemplazos_validos'])
            
            if not reemplazos.issubset(fam_skus):
                print(f"FAIL para SKU {sku}:")
                print(f"  familia_skus: {fam_skus}")
                print(f"  reemplazos_validos: {reemplazos}")
                print(f"  Faltan en familia: {reemplazos - fam_skus}")
                all_passed = False
                
        if all_passed:
            print("Prueba de subconjunto PASS: reemplazos_validos ES_SUBCONJUNTO_DE familia_skus para TODOS los SKUs procesados.")
        else:
            print("Prueba de subconjunto FAIL.")

if __name__ == "__main__":
    test_subset()
