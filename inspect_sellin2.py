"""
inspect_sellin2.py — Validacion completa de columnas sell in y sell out
"""
import pandas as pd

print("=== SELL IN ===")
df_si = pd.read_csv(
    'data/raw/sellin_historico.csv',
    sep=';', encoding='utf-8-sig', dtype=str, quotechar='"', on_bad_lines='skip'
)
print(f'Columnas ({len(df_si.columns)}): {list(df_si.columns)}')
print(f'Filas: {len(df_si)}')

# Columnas clave
col_mes_si  = df_si.columns[4]   # E = Mes
col_anio_si = df_si.columns[5]   # F = Año  
col_sku_si  = df_si.columns[13]  # N = SKU
col_uds_si  = df_si.columns[20]  # U = Unidades_Confirmadas

print(f'col E(mes)={repr(col_mes_si)}, col F(anio)={repr(col_anio_si)}, col N(sku)={repr(col_sku_si)}, col U(uds)={repr(col_uds_si)}')

# Ver valores unicos de año
print(f'\nAnios disponibles: {sorted(df_si[col_anio_si].dropna().unique())}')
print(f'Meses disponibles: {sorted(df_si[col_mes_si].dropna().str.lower().unique())}')

# SKU 7064349
mask_sku = df_si[col_sku_si].astype(str).str.strip() == '7064349'
print(f'\nFilas con SKU 7064349: {mask_sku.sum()}')
sub_sku = df_si[mask_sku][[col_mes_si, col_anio_si, col_uds_si]].head(10)
print(sub_sku.to_string())

# Filtrar junio 2025 para ese SKU
sub_jun = df_si[mask_sku & 
                (df_si[col_mes_si].astype(str).str.strip().str.lower() == 'junio') &
                (df_si[col_anio_si].astype(str).str.strip() == '2025')]
print(f'\nFilas junio 2025: {len(sub_jun)}')
print(sub_jun[[col_sku_si, col_mes_si, col_anio_si, col_uds_si]].to_string())

# Suma
uds_num = pd.to_numeric(sub_jun[col_uds_si].astype(str).str.replace(r'[^\d-]', '', regex=True), errors='coerce').fillna(0)
print(f'SUMA junio 2025 SKU 7064349: {uds_num.sum()}')

print()
print("=== SELL OUT ===")
df_so = pd.read_csv(
    'data/raw/sellout_historico.csv',
    sep=';', encoding='utf-8-sig', dtype=str, quotechar='"', on_bad_lines='skip',
    nrows=5000  # muestra para ver estructura
)
print(f'Columnas ({len(df_so.columns)}): {list(df_so.columns)}')
# Mostrar con indices
for i, c in enumerate(df_so.columns):
    letra = chr(65+i) if i < 26 else f'A{chr(65+i-26)}'
    print(f'  {letra} (idx {i:2d}): {repr(c)}')

# SKU en sell out
mask_so_sku = df_so.apply(lambda col: col.astype(str).str.strip().eq('7064349').any(), axis=0)
print(f'\nColumnas con valor 7064349: {list(df_so.columns[mask_so_sku])}')
