import pandas as pd
df_so = pd.read_csv('data/raw/sellout_historico.csv', sep=';', encoding='utf-8-sig', dtype=str, quotechar='"', on_bad_lines='skip')
print('Filas totales brutas:', len(df_so))
col_mes = df_so.columns[2]
col_anio = df_so.columns[3]
col_sku = df_so.columns[13]
col_uds = df_so.columns[20]

mask = (df_so[col_sku].astype(str).str.strip() == '7064349') & \
       (df_so[col_mes].astype(str).str.strip().str.lower() == 'junio') & \
       (df_so[col_anio].astype(str).str.strip() == '2025')

filas = df_so[mask]
print('Filas para 7064349 junio 2025:', len(filas))

uds = pd.to_numeric(filas[col_uds].astype(str).str.replace(r'[^\d-]', '', regex=True), errors='coerce').fillna(0)
print('SUMA Cantidad:', uds.sum())

print(filas[[col_sku, col_mes, col_anio, col_uds]].head(20))
