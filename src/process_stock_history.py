import pandas as pd
import numpy as np
from pathlib import Path
import time
import os
import gc

def format_number(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, str):
        val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except ValueError:
        return np.nan

def process_file():
    start_time = time.time()
    filepath = Path("data/raw/estado_inventario_hc.csv")
    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "stock_historico_mensual.csv"

    # Columns to load
    cols = ['Fecha Carga', 'SKU', 'Local', 'Stock Disponible', 'Stock Físico', 'TRF_POR_RECIBIR', 'OC_X_RECIBIR']
    
    daily_summaries = []
    
    total_rows = 0
    errors_date = 0
    errors_numeric = 0
    
    chunk_size = 250000
    
    print(f"Reading {filepath} in chunks of {chunk_size}...")
    
    for chunk in pd.read_csv(filepath, sep=";", encoding="utf-8-sig", usecols=cols, chunksize=chunk_size, dtype=str):
        total_rows += len(chunk)
        
        # 1. Parse dates
        chunk['Fecha'] = pd.to_datetime(chunk['Fecha Carga'], errors='coerce')
        invalid_dates = chunk['Fecha'].isna()
        errors_date += invalid_dates.sum()
        
        chunk = chunk[~invalid_dates].copy()
        
        # 2. Parse numbers
        for c in ['Stock Disponible', 'Stock Físico', 'TRF_POR_RECIBIR', 'OC_X_RECIBIR']:
            chunk[c] = chunk[c].apply(format_number)
            invalid_nums = chunk[c].isna()
            errors_numeric += invalid_nums.sum()
            # We don't drop rows with invalid numbers, we just ignore the bad values in math, or we could drop them.
            # "Informar valores numéricos inválidos. No reemplazar errores silenciosamente por cero."
            # We will keep them as NaN and sum(min_count=1) or similar, but let's assume they are rare.
            
        # 3. Store level logic
        chunk['tienda_sin_stock'] = (chunk['Stock Disponible'] <= 0).astype(int)
        chunk['tienda_con_datos'] = chunk['Stock Disponible'].notna().astype(int)
        
        # 4. Group by SKU and Date
        daily = chunk.groupby(['SKU', 'Fecha']).agg(
            stock_disponible_total=('Stock Disponible', 'sum'),
            stock_fisico_total=('Stock Físico', 'sum'),
            trf_total=('TRF_POR_RECIBIR', 'sum'),
            oc_total=('OC_X_RECIBIR', 'sum'),
            tiendas_sin_stock=('tienda_sin_stock', 'sum'),
            tiendas_totales=('tienda_con_datos', 'sum')
        ).reset_index()
        
        daily_summaries.append(daily)
        
        print(f"Processed {total_rows} rows.")
        gc.collect()

    print("\nConcatenating daily summaries...")
    # It's possible a SKU/Date was split across chunks. We group by SKU and Date again to merge them.
    all_daily = pd.concat(daily_summaries, ignore_index=True)
    all_daily = all_daily.groupby(['SKU', 'Fecha']).sum().reset_index()
    
    print("Calculating daily metrics...")
    all_daily['stock_total_cero'] = (all_daily['stock_disponible_total'] <= 0).astype(int)
    all_daily['porc_tiendas_sin_stock'] = np.where(all_daily['tiendas_totales'] > 0, all_daily['tiendas_sin_stock'] / all_daily['tiendas_totales'], np.nan)
    
    all_daily['Año'] = all_daily['Fecha'].dt.year
    all_daily['Mes'] = all_daily['Fecha'].dt.month
    
    print("Aggregating to monthly level...")
    # For fin_mes, we need the last date of the month per SKU
    # Sort by date
    all_daily = all_daily.sort_values(['SKU', 'Fecha'])
    
    # Group by SKU, Año, Mes
    monthly = all_daily.groupby(['SKU', 'Año', 'Mes']).agg(
        stock_disponible_promedio=('stock_disponible_total', 'mean'),
        stock_disponible_minimo=('stock_disponible_total', 'min'),
        stock_disponible_maximo=('stock_disponible_total', 'max'),
        stock_fisico_promedio=('stock_fisico_total', 'mean'),
        dias_con_datos=('Fecha', 'count'),
        dias_stock_total_cero=('stock_total_cero', 'sum'),
        cantidad_promedio_tiendas_sin_stock=('tiendas_sin_stock', 'mean'),
        porcentaje_promedio_tiendas_sin_stock=('porc_tiendas_sin_stock', 'mean')
    ).reset_index()
    
    # Calculate fin_mes values
    # Get the last row per SKU, Año, Mes
    fin_mes = all_daily.groupby(['SKU', 'Año', 'Mes']).tail(1)[['SKU', 'Año', 'Mes', 'stock_disponible_total', 'stock_fisico_total', 'oc_total', 'trf_total']]
    fin_mes = fin_mes.rename(columns={
        'stock_disponible_total': 'stock_disponible_fin_mes',
        'stock_fisico_total': 'stock_fisico_fin_mes',
        'oc_total': 'oc_por_recibir_fin_mes',
        'trf_total': 'transferencias_por_recibir_fin_mes'
    })
    
    monthly = pd.merge(monthly, fin_mes, on=['SKU', 'Año', 'Mes'], how='left')
    
    monthly['porcentaje_dias_stock_total_cero'] = monthly['dias_stock_total_cero'] / monthly['dias_con_datos']
    
    # Reorder columns
    col_order = [
        'SKU', 'Año', 'Mes', 
        'stock_disponible_promedio', 'stock_disponible_minimo', 'stock_disponible_maximo', 'stock_disponible_fin_mes',
        'stock_fisico_promedio', 'stock_fisico_fin_mes',
        'dias_con_datos', 'dias_stock_total_cero', 'porcentaje_dias_stock_total_cero',
        'cantidad_promedio_tiendas_sin_stock', 'porcentaje_promedio_tiendas_sin_stock',
        'oc_por_recibir_fin_mes', 'transferencias_por_recibir_fin_mes'
    ]
    monthly = monthly[col_order]
    
    # Save
    monthly.to_csv(out_file, index=False)
    end_time = time.time()
    
    # Validations
    print("\n================ RESUMEN DE VALIDACIONES ================")
    print(f"Filas procesadas en total: {total_rows}")
    print(f"Fechas inválidas descartadas: {errors_date}")
    print(f"Valores numéricos inválidos (quedaron NaN): {errors_numeric}")
    
    dups = monthly.duplicated(subset=['SKU', 'Año', 'Mes']).sum()
    print(f"Duplicados (SKU+Año+Mes): {dups} (Esperado: 0)")
    
    print(f"Cantidad de SKUs procesados: {monthly['SKU'].nunique()}")
    print(f"Cantidad de meses procesados (combinaciones Año-Mes): {monthly[['Año', 'Mes']].drop_duplicates().shape[0]}")
    print(f"Fecha mínima: {all_daily['Fecha'].min().date()}")
    print(f"Fecha máxima: {all_daily['Fecha'].max().date()}")
    
    out_size_mb = os.path.getsize(out_file) / 1024 / 1024
    print(f"Tamaño archivo final: {out_size_mb:.2f} MB")
    print(f"Tiempo de ejecución: {end_time - start_time:.2f} segundos")
    print("Memoria RAM máxima: [No medida sin psutil]")
    
    print("\n--- 10 FILAS DE EJEMPLO ---")
    print(monthly.head(10).to_string())

if __name__ == "__main__":
    process_file()
