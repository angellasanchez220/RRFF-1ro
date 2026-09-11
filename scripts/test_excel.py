import sys
import os
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.db import engine
from sqlalchemy import text
import openpyxl
from src.services.excel_export_service import get_sku_export_data
from src.services.maquila_service import build_maquila_families
import pandas as pd

def test_excel():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM receta_maquila_componentes WHERE sku_componente IN ('344578X', '5522900')"))
        conn.execute(text("DELETE FROM recetas_maquila WHERE descripcion = 'Test Excel'"))
        
        rid = conn.execute(text("""
            INSERT INTO recetas_maquila (sku_maquilable, descripcion, activa) 
            VALUES ('FAM-EXCEL', 'Test Excel', True) RETURNING id
        """)).fetchone()[0]
        
        conn.execute(text("""
            INSERT INTO receta_maquila_componentes (receta_id, sku_componente, cantidad_por_unidad, no_transformable)
            VALUES 
            (:rid, '344578X', 1.0, False),
            (:rid, '5522900', 1.0, True)
        """), {"rid": rid})

    print("Familia insertada para Excel (344578X, 5522900).")

    with engine.connect() as conn:
        df_sop = pd.read_sql(text("SELECT sku, nombre_producto, stock_act, total_4_sem_verificado as ritmo_mensual FROM planificacion_sop"), conn)
        df_sop['sku'] = df_sop['sku'].astype(str)
        lookup = df_sop.set_index("sku").to_dict("index")
        
        familias_map = build_maquila_families(conn, lookup)
        
    print("\n--- Excel para SKU Transformable (344578X) ---")
    data_t = get_sku_export_data('344578X', familias_map)
    print("Observacion:")
    print(data_t.get('obs', ''))
    
    print("\n--- Excel para SKU No Transformable (5522900) ---")
    data_nt = get_sku_export_data('5522900', familias_map)
    print("Observacion:")
    print(data_nt.get('obs', ''))

if __name__ == "__main__":
    test_excel()
