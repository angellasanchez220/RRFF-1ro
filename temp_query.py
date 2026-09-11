import pandas as pd
from sqlalchemy import create_engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/RRFF_AS_db')
df = pd.read_sql("SELECT sku, sugerencia_compra_dinamica FROM planificacion_sop WHERE sku IN ('7064195', '7846452', '7846460', '7695519', '7877366', '7877374')", engine)
print(df)
