import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM planificacion_sop WHERE sku='F7466' OR codigo_femaco='F7466'", engine)
print(df[['sku', 'codigo_femaco', 'sellin_sep_2026', 'sellout_sep_2026', 'cantidad_transito']].to_dict('records'))
