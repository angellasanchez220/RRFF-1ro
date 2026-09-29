import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT * FROM planificacion_sop WHERE sku='7768311'", engine)
row = df.iloc[0].to_dict()
for k, v in row.items():
    if isinstance(v, (int, float)) and v > 4000:
        print(f"{k}: {v}")
