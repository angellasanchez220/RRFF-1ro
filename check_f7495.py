import pandas as pd
from api.db import engine
df = pd.read_sql("SELECT sku, codigo_femaco, nombre_producto FROM planificacion_sop WHERE codigo_femaco='F7495' OR sku='7780516'", engine)
print(df)
