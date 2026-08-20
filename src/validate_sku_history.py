import pandas as pd
import numpy as np

def validate_history():
    print("Cargando maestro_productos.csv...")
    try:
        maestro = pd.read_csv("data/raw/maestro_productos.csv", sep=";", encoding="utf-8-sig", dtype=str)
        # Handle column name variations
        estado_col = 'Estado' if 'Estado' in maestro.columns else None
        sku_col = 'SKU' if 'SKU' in maestro.columns else maestro.columns[0]
        if estado_col:
            maestro_dict = maestro.set_index(sku_col)[estado_col].to_dict()
        else:
            maestro_dict = {}
        maestro_skus = set(maestro[sku_col].unique())
    except Exception as e:
        print(f"Error cargando maestro: {e}")
        maestro_dict = {}
        maestro_skus = set()

    print("Cargando historial_mensual_sku.csv...")
    df = pd.read_csv("data/processed/historial_mensual_sku.csv")
    
    # Identify SKUs that have stock history
    skus_con_stock = set(df[~df['falta_stock']]['sku'].unique())

    # Get observable period per SKU
    period_df = df.groupby('sku')['fecha_mes'].agg(['min', 'max']).reset_index()
    period_dict = {row['sku']: f"{row['min']} a {row['max']}" for _, row in period_df.iterrows()}
    
    print("Aplicando reglas de validación y completando grid de meses...")
    
    # Optional: fill missing months (grid)
    # We create a full grid for each SKU from its min to max month
    all_rows = []
    for sku, group in df.groupby('sku'):
        min_date = group['fecha_mes'].min()
        max_date = group['fecha_mes'].max()
        # Generate range of months
        # Convert to datetime to generate period range
        dr = pd.period_range(start=min_date, end=max_date, freq='M').strftime('%Y-%m')
        # Merge with existing
        grid = pd.DataFrame({'sku': sku, 'fecha_mes': dr})
        group = pd.merge(grid, group, on=['sku', 'fecha_mes'], how='left')
        
        # Fill anio and mes for missing rows
        if group['anio'].isna().any():
            group['anio'] = group['fecha_mes'].str[:4].astype(int)
            group['mes'] = group['fecha_mes'].str[5:].astype(int)
            
        all_rows.append(group)
        
    df = pd.concat(all_rows, ignore_index=True)
    
    # Initialize flags
    df['sku_en_maestro'] = df['sku'].isin(maestro_skus)
    df['estado_sku'] = df['sku'].map(lambda x: maestro_dict.get(x, 'Desconocido'))
    df['sku_con_stock_historico'] = df['sku'].isin(skus_con_stock)
    df['periodo_observable'] = df['sku'].map(period_dict)
    
    df['sellout_cero_inferido'] = False
    df['sellin_cero_inferido'] = False
    df['sellout_dato_desconocido'] = False
    df['sellin_dato_desconocido'] = False
    
    # We must treat NaNs in sellout and sellin
    # A missing row that we just created will have NaN in sellout, sellin, etc.
    # Also update 'falta_sellout' and 'falta_sellin' for new rows
    df['falta_sellout'] = df['sellout'].isna()
    df['falta_sellin'] = df['sellin'].isna()
    df['falta_stock'] = df['stock_disponible_promedio'].isna()

    # Rule application
    # Active SKUs are 'Mix', 'Activo', etc. Not 'Descontinuado'.
    active_mask = ~df['estado_sku'].str.lower().isin(['descontinuado', 'desconocido'])
    
    # For sellout
    sellout_infer = df['falta_sellout'] & active_mask
    sellout_unk = df['falta_sellout'] & ~active_mask
    
    df.loc[sellout_infer, 'sellout'] = 0.0
    df.loc[sellout_infer, 'sellout_cero_inferido'] = True
    df.loc[sellout_unk, 'sellout_dato_desconocido'] = True

    # For sellin
    sellin_infer = df['falta_sellin'] & active_mask
    sellin_unk = df['falta_sellin'] & ~active_mask
    
    df.loc[sellin_infer, 'sellin'] = 0.0
    df.loc[sellin_infer, 'sellin_cero_inferido'] = True
    df.loc[sellin_unk, 'sellin_dato_desconocido'] = True

    print("Guardando resultado...")
    df.to_csv("data/processed/historial_mensual_sku_validado.csv", index=False)

    print("\n================ RESUMEN DE VALIDACIONES ================")
    print(f"Sell-Out NaN convertidos a cero: {df['sellout_cero_inferido'].sum()}")
    print(f"Sell-In NaN convertidos a cero: {df['sellin_cero_inferido'].sum()}")
    print(f"Sell-Out desconocidos (mantenidos NaN): {df['sellout_dato_desconocido'].sum()}")
    print(f"Sell-In desconocidos (mantenidos NaN): {df['sellin_dato_desconocido'].sum()}")
    
    skus_df = df[['sku', 'estado_sku']].drop_duplicates()
    activos = skus_df[~skus_df['estado_sku'].str.lower().isin(['descontinuado', 'desconocido'])].shape[0]
    descontinuados = skus_df[skus_df['estado_sku'].str.lower() == 'descontinuado'].shape[0]
    desconocidos = skus_df[skus_df['estado_sku'].str.lower() == 'desconocido'].shape[0]
    
    print(f"SKUs activos (Mix/Activo): {activos}")
    print(f"SKUs descontinuados: {descontinuados}")
    print(f"SKUs sin estado conocido: {desconocidos}")
    
    print("Regla aplicada: Cero inferido solo si SKU está Activo/Mix y dentro de su periodo observable. De lo contrario, se mantiene NaN (Desconocido). Se rellenaron los meses sin movimiento creando un grid continuo.")
    print("Ambigüedades pendientes: Las fechas exactas de descontinuación no están en maestro_productos.csv, por lo que los SKUs descontinuados mantienen NaN en todo su periodo sin datos, sin poder saber si en algún mes anterior aún estaban activos y vendían 0.")
    
    print("\n--- 5 Ejemplos: Cero inferido en Sell-Out ---")
    print(df[df['sellout_cero_inferido']].head(5)[['sku', 'fecha_mes', 'estado_sku', 'sellout', 'sellout_cero_inferido']])
    
    print("\n--- 5 Ejemplos: Dato desconocido en Sell-Out ---")
    print(df[df['sellout_dato_desconocido']].head(5)[['sku', 'fecha_mes', 'estado_sku', 'sellout', 'sellout_dato_desconocido']])
    
    print("\n--- 5 Ejemplos: SKU descontinuado ---")
    print(df[df['estado_sku'].str.lower() == 'descontinuado'].head(5)[['sku', 'fecha_mes', 'estado_sku', 'sellout']])
    
    print("\n--- 5 Ejemplos: SKU sin stock histórico ---")
    print(df[~df['sku_con_stock_historico']].head(5)[['sku', 'fecha_mes', 'sku_con_stock_historico', 'falta_stock']])

if __name__ == "__main__":
    validate_history()
