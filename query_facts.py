import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM fact_transito WHERE sku='7768311'", engine)
print("TRANSITO:", df.to_dict('records'))
df = pd.read_sql("SELECT * FROM fact_ventas WHERE sku='7768311'", engine)
print("VENTAS:", df.to_dict('records'))
