import sys
sys.path.append('api')
from db import engine
import pandas as pd

df1 = pd.read_sql('SELECT COUNT(*) FROM recetas_maquila', engine)
df2 = pd.read_sql('SELECT COUNT(*) FROM receta_maquila_componentes', engine)
print('recetas_maquila:', df1.iloc[0,0], 'componentes:', df2.iloc[0,0])
