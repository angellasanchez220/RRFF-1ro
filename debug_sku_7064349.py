from api.db import engine
from sqlalchemy import text
import pandas as pd
with engine.connect() as conn:
    df = pd.read_sql(text("SELECT * FROM planificacion_sop WHERE sku='7064349'"), conn)
    row = df.iloc[0]
    print('--- DATOS SEMANALES ---')
    for i in range(1, 5):
        print(f'sem{i}_uds: {row[f"sem{i}_uds"]}')
    print('total_4_sem_verificado:', row['total_4_sem_verificado'])
    print('\n--- DATOS PROYECTADOS ---')
    for col in ['sellout_may_2026', 'sellout_jun_2026', 'sellout_jul_2026', 'sellout_ago_2026']:
        print(f'{col}: {row[col]}')
    print('\n--- OTROS ---')
    print('stock_act:', row['stock_act'])
    print('cantidad_transito:', row['cantidad_transito'])
    print('ump:', row['ump'])
    print('sug_ritmo_pasado:', row['sug_ritmo_pasado'])
    print('sug_ritmo_futuro:', row['sug_ritmo_futuro'])
    print('sug_ritmo_mensual:', row['sug_ritmo_mensual'])
    print('sug_target_uds:', row['sug_target_uds'])
    print('sugerencia_compra_inmediata_uds:', row['sugerencia_compra_inmediata_uds'])
