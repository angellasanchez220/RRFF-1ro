import pandas as pd
from api.db import engine
df = pd.read_sql("SELECT sku, codigo_femaco FROM planificacion_sop WHERE sku IN ('5522900','T1001','344578X','C9402') OR codigo_femaco IN ('5522900','T1001','344578X','C9402')", engine)
print(df)
