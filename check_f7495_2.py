import pandas as pd
from api.db import engine
df = pd.read_sql("SELECT * FROM recetas_maquila WHERE sku_maquilable IN ('7780516','F7495')", engine)
print(df)
