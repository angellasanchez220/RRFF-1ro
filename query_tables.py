import sys
sys.path.append('api')
from db import engine
import pandas as pd
df = pd.read_sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public'", engine)
print(df['table_name'].tolist())
