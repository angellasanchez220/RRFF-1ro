import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM fact_transito LIMIT 1", engine)
print(df.columns.tolist())
