import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM fact_compras WHERE sku='7768311'", engine)
print(df.to_dict('records'))
