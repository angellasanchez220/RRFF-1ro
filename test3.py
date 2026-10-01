import sys
sys.path.append('api')
from db import engine
import pandas as pd
from src.services.maquila_service import build_product_lookup_by_internal_code, build_maquila_families

df = pd.read_sql("SELECT * FROM planificacion_sop WHERE sku='5522900' OR codigo_femaco='T1001'", engine)
lookup_dict = build_product_lookup_by_internal_code(df, ritmo_col='total_4_sem_verificado')
print('LOOKUP KEYS:', list(lookup_dict.keys()))

with engine.connect() as conn:
    fm = build_maquila_families(conn, lookup_dict)

print('FM KEYS:', list(fm.keys()))
print('FAMILIA PARA T1001:', fm.get('T1001', {}).get('cantidad_miembros', 0))
print('FAMILIA PARA 5522900:', fm.get('5522900', {}).get('cantidad_miembros', 0))
