import pandas as pd
from api.db import engine
df = pd.read_sql("SELECT * FROM receta_maquila_componentes WHERE sku_componente IN ('7780516','F7495')", engine)
print(df)
