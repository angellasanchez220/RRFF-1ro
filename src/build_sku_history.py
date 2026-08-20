import pandas as pd
import numpy as np
from pathlib import Path
import calendar
import time

def parse_num(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, str):
        val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except ValueError:
        return np.nan

def get_business_days_in_month(year, month):
    try:
        if pd.isna(year) or pd.isna(month): return 22
        start = f"{int(year)}-{int(month):02d}-01"
        next_month = pd.to_datetime(start) + pd.offsets.MonthBegin(1)
        return np.busday_count(start, next_month.strftime("%Y-%m-%d"))
    except:
        return 22

def build_history():
    start = time.time()
    
    # 1. Process Sell-out
    print("Procesando Sell-Out...")
    sellout_chunks = []
    # sellout_historico.csv is ~394MB, read in chunks
    for chunk in pd.read_csv("data/raw/sellout_historico.csv", sep=";", encoding="utf-8-sig", chunksize=250000, dtype=str):
        if 'Fecha' not in chunk.columns or 'SKU' not in chunk.columns or 'Cantidad' not in chunk.columns:
            continue
        chunk['Fecha'] = pd.to_datetime(chunk['Fecha'], errors='coerce')
        chunk = chunk.dropna(subset=['Fecha', 'SKU'])
        chunk['Cantidad'] = chunk['Cantidad'].apply(parse_num)
        chunk['Año'] = chunk['Fecha'].dt.year
        chunk['Mes'] = chunk['Fecha'].dt.month
        # Aggregate by chunk
        agg = chunk.groupby(['SKU', 'Año', 'Mes'])['Cantidad'].sum().reset_index()
        sellout_chunks.append(agg)
    
    if sellout_chunks:
        df_sellout = pd.concat(sellout_chunks, ignore_index=True)
        df_sellout = df_sellout.groupby(['SKU', 'Año', 'Mes'])['Cantidad'].sum().reset_index()
        df_sellout.rename(columns={'Cantidad': 'sellout'}, inplace=True)
    else:
        df_sellout = pd.DataFrame(columns=['SKU', 'Año', 'Mes', 'sellout'])

    # 2. Process Sell-in
    print("Procesando Sell-In...")
    # sellin_historico is ~28MB, we can read fully
    try:
        df_sellin_raw = pd.read_csv("data/raw/sellin_historico.csv", sep=";", encoding="utf-8-sig", dtype=str)
        df_sellin_raw['Fecha_carga'] = pd.to_datetime(df_sellin_raw['Fecha_carga'], errors='coerce')
        df_sellin_raw = df_sellin_raw.dropna(subset=['Fecha_carga', 'SKU'])
        # Prefer Unidades_Confirmadas over Unidades_Informadas if available
        if 'Unidades_Confirmadas' in df_sellin_raw.columns:
            qty_col = 'Unidades_Confirmadas'
        elif 'Unidades_Informadas' in df_sellin_raw.columns:
            qty_col = 'Unidades_Informadas'
        else:
            qty_col = None
            
        if qty_col:
            df_sellin_raw[qty_col] = df_sellin_raw[qty_col].apply(parse_num)
            df_sellin_raw['Año'] = df_sellin_raw['Fecha_carga'].dt.year
            df_sellin_raw['Mes'] = df_sellin_raw['Fecha_carga'].dt.month
            df_sellin = df_sellin_raw.groupby(['SKU', 'Año', 'Mes'])[qty_col].sum().reset_index()
            df_sellin.rename(columns={qty_col: 'sellin'}, inplace=True)
        else:
            df_sellin = pd.DataFrame(columns=['SKU', 'Año', 'Mes', 'sellin'])
    except Exception as e:
        print(f"Error procesando Sell-in: {e}")
        df_sellin = pd.DataFrame(columns=['SKU', 'Año', 'Mes', 'sellin'])

    # 3. Load Stock Processed
    print("Cargando Stock Histórico Mensual...")
    df_stock = pd.read_csv("data/processed/stock_historico_mensual.csv")

    # 4. Merge all on SKU, Año, Mes
    print("Fusionando datos...")
    # Ensure types match
    df_sellout['Año'] = df_sellout['Año'].astype(float)
    df_sellout['Mes'] = df_sellout['Mes'].astype(float)
    df_sellin['Año'] = df_sellin['Año'].astype(float)
    df_sellin['Mes'] = df_sellin['Mes'].astype(float)
    df_stock['Año'] = df_stock['Año'].astype(float)
    df_stock['Mes'] = df_stock['Mes'].astype(float)

    merged = pd.merge(df_sellout, df_sellin, on=['SKU', 'Año', 'Mes'], how='outer')
    merged = pd.merge(merged, df_stock, on=['SKU', 'Año', 'Mes'], how='outer')

    # Convert Año and Mes to int for cleaner output (ignoring NaNs for conversion)
    merged['Año'] = merged['Año'].fillna(0).astype(int)
    merged['Mes'] = merged['Mes'].fillna(0).astype(int)
    merged = merged[(merged['Año'] > 0) & (merged['Mes'] > 0)]

    # 5. Create derived columns
    print("Calculando columnas derivadas...")
    # fecha_mes -> YYYY-MM
    merged['fecha_mes'] = merged['Año'].astype(str) + "-" + merged['Mes'].astype(str).str.zfill(2)
    
    # mes_completo = dias_con_datos_stock >= 0.8 * business_days_in_month
    merged['dias_mes_habiles'] = merged.apply(lambda row: get_business_days_in_month(row['Año'], row['Mes']), axis=1)
    merged['mes_completo'] = merged['dias_con_datos'] >= (0.8 * merged['dias_mes_habiles'])
    merged['mes_completo'] = merged['mes_completo'].fillna(False)

    # Missing flags
    merged['falta_sellout'] = merged['sellout'].isna()
    merged['falta_sellin'] = merged['sellin'].isna()
    merged['falta_stock'] = merged['stock_disponible_promedio'].isna()

    # Reorder columns
    base_cols = [
        'SKU', 'Año', 'Mes', 'fecha_mes', 'sellout', 'sellin',
        'stock_disponible_promedio', 'stock_disponible_minimo', 'stock_disponible_maximo', 'stock_disponible_fin_mes',
        'stock_fisico_promedio', 'stock_fisico_fin_mes', 'dias_con_datos',
        'dias_stock_total_cero', 'porcentaje_dias_stock_total_cero',
        'cantidad_promedio_tiendas_sin_stock', 'porcentaje_promedio_tiendas_sin_stock',
        'oc_por_recibir_fin_mes', 'transferencias_por_recibir_fin_mes',
        'mes_completo', 'falta_sellout', 'falta_sellin', 'falta_stock'
    ]
    # In case there are some missing columns from stock, we only select what's available
    final_cols = [c for c in base_cols if c in merged.columns]
    
    # Rename 'SKU' to 'sku', 'Año' to 'anio', 'Mes' to 'mes'
    merged = merged.rename(columns={'SKU': 'sku', 'Año': 'anio', 'Mes': 'mes'})
    final_cols = [c.replace('SKU', 'sku').replace('Año', 'anio').replace('Mes', 'mes') for c in final_cols]
    
    merged = merged[final_cols]
    
    # Sort
    merged = merged.sort_values(['sku', 'anio', 'mes'])
    
    # Save
    out_file = "data/processed/historial_mensual_sku.csv"
    merged.to_csv(out_file, index=False)
    
    end = time.time()

    # 6. Validations
    print("\n================ RESUMEN DE VALIDACIONES ================")
    dups = merged.duplicated(subset=['sku', 'anio', 'mes']).sum()
    print(f"Duplicados (SKU+Año+Mes): {dups} (Esperado: 0)")
    print(f"Cantidad total de filas: {len(merged)}")
    print(f"Cantidad total de SKUs: {merged['sku'].nunique()}")
    print(f"Periodo mínimo: {merged['fecha_mes'].min()} | Máximo: {merged['fecha_mes'].max()}")
    
    completos = merged['mes_completo'].sum()
    incompletos = len(merged) - completos
    print(f"Meses completos: {completos} | Incompletos: {incompletos}")
    
    print(f"Filas sin Sell-Out (falta_sellout): {merged['falta_sellout'].sum()}")
    print(f"Filas sin Sell-In (falta_sellin): {merged['falta_sellin'].sum()}")
    print(f"Filas sin Stock (falta_stock): {merged['falta_stock'].sum()}")
    
    zeros_sellout = (merged['sellout'] == 0).sum()
    print(f"Ceros reales en Sell-Out (no nulos): {zeros_sellout}")
    
    print(f"Tiempo de ejecución: {end - start:.2f} segundos")
    
    print("\n--- 10 FILAS DE EJEMPLO ---")
    print(merged.head(10).to_string())

if __name__ == "__main__":
    build_history()
