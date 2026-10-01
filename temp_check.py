import pandas as pd
from api.db import engine
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_colwidth', None)
df = pd.read_sql("SELECT * FROM planificacion_sop WHERE codigo_femaco='C9411'", engine)
for col in df.columns:
    print(f"{col}: {df[col].iloc[0]}")
