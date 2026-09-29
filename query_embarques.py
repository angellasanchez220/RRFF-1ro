import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM control_embarques WHERE sku='7768311' OR codigo_femaco='F7466'", engine)
print(df.to_dict('records'))
