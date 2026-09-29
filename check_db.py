import sys
sys.path.append('api')
from db import engine
import pandas as pd

df = pd.read_sql("""
    SELECT r.id, r.sku_maquilable, r.activa, c.sku_componente
    FROM recetas_maquila r 
    JOIN receta_maquila_componentes c ON c.receta_id = r.id
""", engine)
print(df.to_dict('records'))
