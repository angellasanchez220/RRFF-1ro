import pandas as pd
from sqlalchemy import create_engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/RRFF_AS_db')
df = pd.read_sql("SELECT sku, COUNT(*) FROM planificacion_sop GROUP BY sku HAVING COUNT(*) > 1", engine)
print("Duplicates in planificacion_sop:")
print(df)
