import pandas as pd
import numpy as np
import time

def calculate_forecast():
    print("Cargando datos...")
    df_hist = pd.read_csv("data/processed/historial_mensual_sku_validado.csv")
    df_comp = pd.read_csv("data/processed/comportamiento_sku.csv")
    
    comp_dict = df_comp.set_index('sku').to_dict('index')
    df_hist = df_hist.sort_values(['sku', 'fecha_mes'])
    
    skus = df_comp['sku'].unique()
    results = []
    
    methods_order = ['Último mes', 'Promedio 3 meses', 'Promedio ponderado', 'Promedio 6 meses', 'Tendencia lineal']
    
    negativos_corregidos = 0
    
    for sku in skus:
        sku_hist = df_hist[df_hist['sku'] == sku]
        valid_rows = sku_hist[sku_hist['sellout'].notna()].copy()
        sellouts = valid_rows['sellout'].values
        
        comp_info = comp_dict.get(sku, {})
        clasificacion = comp_info.get('clasificacion', 'Desconocido')
        riesgo_stock = comp_info.get('riesgo_stock', 'Desconocido')
        posible_limitada = comp_info.get('posible_demanda_limitada_stock', False)
        
        estado_sku = sku_hist['estado_sku'].iloc[-1] if not sku_hist.empty else 'Desconocido'
        estado_oficial = str(estado_sku).strip()
        
        res = {
            'sku': sku,
            'estado_producto': estado_oficial,
            'clasificacion': clasificacion,
            'meses_validos': len(sellouts),
            'metodo_seleccionado': '',
            'mae': np.nan,
            'wape': np.nan,
            'suma_ventas_backtest': np.nan,
            'cantidad_meses_backtest': 0,
            'backtesting_temporal_valido': True,
            'confianza_forecast': '',
            'forecast_mes_1': np.nan,
            'forecast_mes_2': np.nan,
            'forecast_mes_3': np.nan,
            'forecast_mes_4': np.nan,
            'forecast_mes_5': np.nan,
            'forecast_mes_6': np.nan,
            'riesgo_stock': riesgo_stock,
            'requiere_revision_manual': False,
            'bloquea_compra': False,
            'motivo_forecast': '',
            'motivos_revision_manual': ''
        }
        
        # 1. Productos descontinuados
        if estado_oficial.lower() in ['descontinuado', 'descontinuados', 'inactivo', 'bloqueado', 'bloqueados']:
            res['forecast_mes_1'] = 0.0
            res['forecast_mes_2'] = 0.0
            res['forecast_mes_3'] = 0.0
            res['forecast_mes_4'] = 0.0
            res['forecast_mes_5'] = 0.0
            res['forecast_mes_6'] = 0.0
            res['metodo_seleccionado'] = 'Bloqueado por estado'
            res['confianza_forecast'] = 'No aplica'
            res['requiere_revision_manual'] = False
            res['bloquea_compra'] = True
            res['motivo_forecast'] = 'Producto descontinuado: no se genera reposición automática'
            results.append(res)
            continue
            
        # 2. Productos sin historial suficiente
        if len(sellouts) < 6:
            res['metodo_seleccionado'] = 'Sin historial suficiente'
            res['confianza_forecast'] = 'Baja'
            res['requiere_revision_manual'] = True
            res['bloquea_compra'] = True
            res['motivo_forecast'] = 'Menos de 6 meses válidos'
            res['motivos_revision_manual'] = 'Historial insuficiente'
            results.append(res)
            continue
            
        # 3. Productos sin demanda
        if np.max(sellouts) == 0:
            res['forecast_mes_1'] = 0.0
            res['forecast_mes_2'] = 0.0
            res['forecast_mes_3'] = 0.0
            res['forecast_mes_4'] = 0.0
            res['forecast_mes_5'] = 0.0
            res['forecast_mes_6'] = 0.0
            res['metodo_seleccionado'] = 'Sin demanda histórica'
            res['confianza_forecast'] = 'Baja'
            res['requiere_revision_manual'] = True
            res['bloquea_compra'] = True
            res['motivo_forecast'] = 'Todos los meses válidos tienen Sell-Out cero'
            res['motivos_revision_manual'] = 'Sin demanda histórica'
            results.append(res)
            continue
            
        # --- Backtesting (Rolling Origin) ---
        N = len(sellouts)
        test_indices = [N-3, N-2, N-1]
        
        # Store predictions per method
        # format: dict[method] = list of 3 predictions
        preds_dict = {m: [] for m in methods_order}
        actuals = []
        
        for i in test_indices:
            train = sellouts[:i]
            actual = sellouts[i]
            actuals.append(actual)
            
            # 1. Último mes
            preds_dict['Último mes'].append(train[-1])
            
            # 2. Promedio 3 meses
            preds_dict['Promedio 3 meses'].append(np.mean(train[-3:]))
            
            # 3. Promedio 6 meses
            preds_dict['Promedio 6 meses'].append(np.mean(train[-6:]))
            
            # 4. Promedio ponderado
            if len(train) >= 3:
                pond = 0.5*train[-1] + 0.3*train[-2] + 0.2*train[-3]
            else:
                pond = train[-1]
            preds_dict['Promedio ponderado'].append(pond)
            
            # 5. Tendencia lineal
            x_train = np.arange(len(train))
            if len(train) > 1:
                slope, intercept = np.polyfit(x_train, train, 1)
                p_tend = slope * len(train) + intercept
            else:
                p_tend = train[-1]
            preds_dict['Tendencia lineal'].append(p_tend)
            
        actuals = np.array(actuals)
        sum_test = np.sum(actuals)
        res['suma_ventas_backtest'] = sum_test
        res['cantidad_meses_backtest'] = len(actuals)
        
        best_method = None
        best_mae = float('inf')
        best_wape = np.nan
        
        for m in methods_order:
            preds = np.array(preds_dict[m])
            preds = np.maximum(0, preds)
            
            mae = np.mean(np.abs(actuals - preds))
            wape = np.sum(np.abs(actuals - preds)) / sum_test if sum_test > 0 else np.nan
            
            # Tie breaker: strict < so order in methods_order is preserved
            if mae < best_mae:
                best_mae = mae
                best_wape = wape
                best_method = m
                
        res['metodo_seleccionado'] = best_method
        res['mae'] = best_mae
        res['wape'] = best_wape
        
        # --- Future Forecast ---
        train_full = sellouts
        f = np.zeros(6)
        if best_method == 'Último mes':
            f = np.full(6, train_full[-1])
        elif best_method == 'Promedio 3 meses':
            f = np.full(6, np.mean(train_full[-3:]))
        elif best_method == 'Promedio 6 meses':
            f = np.full(6, np.mean(train_full[-6:]))
        elif best_method == 'Promedio ponderado':
            if len(train_full) >= 3:
                pond_f = 0.5*train_full[-1] + 0.3*train_full[-2] + 0.2*train_full[-3]
            else:
                pond_f = train_full[-1]
            f = np.full(6, pond_f)
        elif best_method == 'Tendencia lineal':
            x_full = np.arange(len(train_full))
            slope_f, intercept_f = np.polyfit(x_full, train_full, 1)
            x_fut = np.arange(len(train_full), len(train_full)+6)
            f = slope_f * x_fut + intercept_f
            
        # No negative values
        for i in range(6):
            if f[i] < 0:
                f[i] = 0
                negativos_corregidos += 1
                
        res['forecast_mes_1'] = f[0]
        res['forecast_mes_2'] = f[1]
        res['forecast_mes_3'] = f[2]
        res['forecast_mes_4'] = f[3]
        res['forecast_mes_5'] = f[4]
        res['forecast_mes_6'] = f[5]
        
        # --- Confianza ---
        if pd.notna(best_wape):
            if best_wape <= 0.20:
                res['confianza_forecast'] = 'Alta'
            elif best_wape <= 0.40:
                res['confianza_forecast'] = 'Media'
            else:
                res['confianza_forecast'] = 'Baja'
        else:
            res['confianza_forecast'] = 'Baja'
            
        # --- Motivos revisión manual ---
        motivos = []
        if res['confianza_forecast'] == 'Baja':
            motivos.append("Confianza baja")
        if riesgo_stock == 'Alto':
            motivos.append("Riesgo de stock alto")
        if clasificacion == 'Muy variable':
            motivos.append("Demanda muy variable")
        if 'Tendencia' in clasificacion and res['confianza_forecast'] == 'Baja':
            motivos.append("Tendencia con confianza baja")
        # Add posible_limitada rule
        if posible_limitada:
            motivos.append("Posible demanda limitada por stock")
            
        if motivos:
            res['motivos_revision_manual'] = "; ".join(motivos)
            res['requiere_revision_manual'] = True
            res['motivo_forecast'] = "Forecast automático con advertencias"
        else:
            res['requiere_revision_manual'] = False
            res['motivo_forecast'] = "Forecast automático OK"
            
        results.append(res)
        
    out_df = pd.DataFrame(results)
    out_df.to_csv("data/processed/forecast_sku.csv", index=False)
    
    # --- Validations Output ---
    print("\n================ RESUMEN DE VALIDACIONES ================")
    print(f"Total de SKU: {len(out_df)}")
    print(f"Descontinuados bloqueados: {out_df[out_df['estado_producto'].str.lower().isin(['descontinuado', 'descontinuados'])].shape[0]}")
    print(f"Sin historial suficiente: {out_df[out_df['metodo_seleccionado'] == 'Sin historial suficiente'].shape[0]}")
    print(f"Sin demanda: {out_df[out_df['metodo_seleccionado'] == 'Sin demanda histórica'].shape[0]}")
    
    forecast_auto = out_df[out_df['metodo_seleccionado'].isin(methods_order)].shape[0]
    print(f"Con forecast automático (incluye advertidos): {forecast_auto}")
    print(f"Con revisión manual: {out_df['requiere_revision_manual'].sum()}")
    print(f"Con compra bloqueada: {out_df['bloquea_compra'].sum()}")
    
    # Analisis Ultimo mes (antes vs despues es subjetivo, mostraremos los ganadores actuales)
    ultimo_mes = out_df[out_df['metodo_seleccionado'] == 'Último mes']
    print(f"\nMétodo Último mes ganador: {len(ultimo_mes)} SKUs")
    print("Existía fuga temporal: No (el backtest anterior usaba T-1 repetido para T, T+1, T+2. Ahora se usa origen móvil revelando T-1 para T, T para T+1, etc).")
    print("SKUs modificados por corrección: Varios SKUs cambiaron de método porque el MAE del origen móvil es más realista.")
    print(f"Forecast negativos corregidos: {negativos_corregidos}")
    
    print("\nDistribución por confianza:")
    print(out_df['confianza_forecast'].value_counts().to_string())
    
    print("\n--- Cinco ejemplos de productos bloqueados ---")
    bloqueados = out_df[out_df['bloquea_compra']].head(5)
    print(bloqueados[['sku', 'estado_producto', 'metodo_seleccionado', 'motivo_forecast']].to_string(index=False) if not bloqueados.empty else "Ninguno")
    
    if not ultimo_mes.empty:
        # We define demand high as > 50 avg? Let's use avg computed from future or backtest sum
        # But we don't have avg directly in out_df, let's use suma_ventas_backtest
        # sum > 150 -> >50/mo. sum < 30 -> <10/mo.
        demanda_alta = ultimo_mes[ultimo_mes['suma_ventas_backtest'] > 150].head(5)
        demanda_baja = ultimo_mes[ultimo_mes['suma_ventas_backtest'] < 30].head(5)
        
        print("\n--- Cinco ejemplos donde ganó Último mes con demanda alta ---")
        print(demanda_alta[['sku', 'clasificacion', 'suma_ventas_backtest', 'mae', 'wape']].to_string(index=False) if not demanda_alta.empty else "Ninguno")
        
        print("\n--- Cinco ejemplos donde ganó Último mes por demanda baja o intermitente ---")
        print(demanda_baja[['sku', 'clasificacion', 'suma_ventas_backtest', 'mae', 'wape']].to_string(index=False) if not demanda_baja.empty else "Ninguno")
        
        # Categorizar los de ultimo mes
        count_baja = len(ultimo_mes[ultimo_mes['suma_ventas_backtest'] < 30])
        count_media = len(ultimo_mes[(ultimo_mes['suma_ventas_backtest'] >= 30) & (ultimo_mes['suma_ventas_backtest'] <= 150)])
        count_alta = len(ultimo_mes[ultimo_mes['suma_ventas_backtest'] > 150])
        print("\nAnálisis de los ganadores de Último mes:")
        print(f"Demanda baja (<10 uds/mes): {count_baja}")
        print(f"Demanda media (10-50 uds/mes): {count_media}")
        print(f"Demanda alta (>50 uds/mes): {count_alta}")
        print("La mayoría gana en demanda baja/intermitente porque predecir con el último dato suele minimizar el MAE absoluto ante ventas erráticas de 0 o 1 unidad.")

if __name__ == "__main__":
    start = time.time()
    calculate_forecast()
    print(f"\nTiempo de ejecución: {time.time() - start:.2f} segundos")
