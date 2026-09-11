import pandas as pd
from sqlalchemy import create_engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/RRFF_AS_db')
df = pd.read_sql("SELECT sku, cantidad FROM control_embarques WHERE sku LIKE '%7064195%'", engine)
print("control_embarques count:", len(df))
print(df)
