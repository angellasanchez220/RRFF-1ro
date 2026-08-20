"""
inspect_sellin.py — Inspecciona columnas del raw sell in y valida dato del usuario
"""
import pandas as pd

# Leer con sep=';', quotechar='"'
df = pd.read_csv(
    'data/raw/sellin_historico.csv',
    sep=';',
    encoding='utf-8-sig',
    dtype=str,
    quotechar='"',
    on_bad_lines='skip'
)
print(f'Total columnas: {len(df.columns)}')
print(f'Total filas: {len(df)}')
print()
for i, c in enumerate(df.columns):
    letra = chr(65+i) if i < 26 else f'A{chr(65+i-26)}'
    print(f'  {letra} (idx {i:2d}): {c}')

print()
print("=== Validacion SKU 7064349 / junio 2025 ===")
# Columna E=idx4 Mes, F=idx5 Año, N=idx13 SKU, U=idx20 Unidades_Confirmadas
col_mes  = df.columns[4]
col_anio = df.columns[5]
col_sku  = df.columns[13]
col_uds  = df.columns[20]

print(f'col_mes={col_mes}, col_anio={col_anio}, col_sku={col_sku}, col_uds={col_uds}')

mask = (
    df[col_sku].astype(str).str.strip() == '7064349'
)
print(f"\nFilas con SKU 7064349: {mask.sum()}")

mask2 = mask & (
    df[col_mes].astype(str).str.strip().str.lower().str.contains('jun') &
    df[col_anio].astype(str).str.strip() == '2025'
)
print(f"Filtrado Junio 2025: {mask2.sum()} filas")
sub = df[mask2][[col_sku, col_mes, col_anio, col_uds]]
print(sub.head(20))

uds_num = pd.to_numeric(
    df.loc[mask2, col_uds].astype(str).str.replace(r'[^\d-]', '', regex=True),
    errors='coerce'
).fillna(0)
print(f"\nSUMA Unidades_Confirmadas junio 2025 SKU 7064349: {uds_num.sum()}")

# Verificar sell out tambien
print("\n=== Sell Out Historico (primeras cols) ===")
df_so = pd.read_csv(
    'data/raw/sellout_historico.csv',
    sep=';', encoding='utf-8-sig', dtype=str, quotechar='"', on_bad_lines='skip'
)
print(f'Sell Out cols: {len(df_so.columns)}')
for i, c in enumerate(df_so.columns[:25]):
    letra = chr(65+i) if i < 26 else f'A{chr(65+i-26)}'
    print(f'  {letra} (idx {i:2d}): {c}')
