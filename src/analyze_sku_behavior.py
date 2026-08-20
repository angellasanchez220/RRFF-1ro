import pandas as pd
import numpy as np
import time

def compute_metrics():
    print("Cargando datos...")
    df = pd.read_csv("data/processed/historial_mensual_sku_validado.csv")
    
    # Sort chronologically to make calculations easier
    df = df.sort_values(['sku', 'fecha_mes'])
    
    results = []
    skus = df['sku'].unique()
    print(f"Procesando {len(skus)} SKUs...")
    
    for sku in skus:
        # Get all rows for SKU
        sku_df_all = df[df['sku'] == sku].copy()
        
        # Valid sellout rows
        sku_df_valid = sku_df_all[sku_df_all['sellout'].notna()].copy()
        sku_df_last12 = sku_df_valid.tail(12).copy()
        
        meses_con_stock_incompleto = (~sku_df_last12['mes_completo']).sum() if not sku_df_last12.empty else 0
        
        # Exclude incomplete months from calculation
        calc_df = sku_df_last12[sku_df_last12['mes_completo']].copy() if not sku_df_last12.empty else pd.DataFrame()
        meses_disponibles = len(calc_df)
        
        res = {
            'sku': sku,
            'meses_con_stock_incompleto': meses_con_stock_incompleto,
            'meses_validos': meses_disponibles,
            'meses_con_venta': 0,
            'meses_sin_venta': 0,
            'venta_promedio_mensual': np.nan,
            'venta_mediana_mensual': np.nan,
            'venta_minima': np.nan,
            'venta_maxima': np.nan,
            'desviacion_estandar_venta': np.nan,
            'coeficiente_variacion': np.nan,
            'promedio_ultimos_3_meses': np.nan,
            'promedio_ultimos_6_meses': np.nan,
            'promedio_ultimos_12_meses': np.nan,
            'cambio_reciente_porcentual': np.nan,
            'pendiente_tendencia': np.nan,
            'porcentaje_meses_sin_venta': np.nan,
            'porcentaje_promedio_tiendas_sin_stock': np.nan,
            'porcentaje_dias_stock_total_cero': np.nan,
            'clasificacion': 'Sin historial suficiente',
            'motivo_clasificacion': 'Menos de 6 meses válidos',
            'riesgo_stock': 'Bajo',
            'confianza_tendencia': np.nan
        }
        
        if meses_disponibles >= 6:
            sellouts = calc_df['sellout'].values
            
            res['meses_con_venta'] = (sellouts > 0).sum()
            res['meses_sin_venta'] = (sellouts == 0).sum()
            res['porcentaje_meses_sin_venta'] = res['meses_sin_venta'] / meses_disponibles
            
            res['venta_promedio_mensual'] = np.mean(sellouts)
            res['venta_mediana_mensual'] = np.median(sellouts)
            res['venta_minima'] = np.min(sellouts)
            res['venta_maxima'] = np.max(sellouts)
            
            if meses_disponibles > 1:
                res['desviacion_estandar_venta'] = np.std(sellouts, ddof=1)
            else:
                res['desviacion_estandar_venta'] = 0.0
                
            if res['venta_promedio_mensual'] > 0:
                res['coeficiente_variacion'] = res['desviacion_estandar_venta'] / res['venta_promedio_mensual']
            else:
                res['coeficiente_variacion'] = np.nan
                
            res['promedio_ultimos_3_meses'] = np.mean(sellouts[-3:])
            res['promedio_ultimos_6_meses'] = np.mean(sellouts[-6:])
            res['promedio_ultimos_12_meses'] = res['venta_promedio_mensual']
            
            if meses_disponibles >= 6:
                prev_3_mean = np.mean(sellouts[-6:-3])
                if prev_3_mean > 0:
                    res['cambio_reciente_porcentual'] = (res['promedio_ultimos_3_meses'] / prev_3_mean) - 1.0
            
            x = np.arange(meses_disponibles)
            slope = np.polyfit(x, sellouts, 1)[0]
            res['pendiente_tendencia'] = slope
            
            # Stock metrics calculation
            pct_tiendas = calc_df['porcentaje_promedio_tiendas_sin_stock'].mean()
            pct_dias_cero = calc_df['porcentaje_dias_stock_total_cero'].mean()
            if pd.isna(pct_tiendas): pct_tiendas = 0
            if pd.isna(pct_dias_cero): pct_dias_cero = 0
            
            res['porcentaje_promedio_tiendas_sin_stock'] = pct_tiendas
            res['porcentaje_dias_stock_total_cero'] = pct_dias_cero
            
            # Riesgo stock
            if pct_tiendas > 0.25 or pct_dias_cero > 0.05:
                res['riesgo_stock'] = 'Alto'
            elif (0.10 <= pct_tiendas <= 0.25) or pct_dias_cero > 0:
                res['riesgo_stock'] = 'Medio'
            else:
                res['riesgo_stock'] = 'Bajo'
                
            # Classification
            if res['venta_maxima'] == 0:
                res['clasificacion'] = 'Sin demanda'
                res['motivo_clasificacion'] = 'Venta máxima = 0'
            elif res['porcentaje_meses_sin_venta'] >= 0.40:
                res['clasificacion'] = 'Intermitente'
                res['motivo_clasificacion'] = '>=40% meses en 0'
            elif res['pendiente_tendencia'] < 0 and pd.notna(res['cambio_reciente_porcentual']) and res['cambio_reciente_porcentual'] <= -0.15:
                res['clasificacion'] = 'Tendencia decreciente'
                res['motivo_clasificacion'] = 'Pendiente negativa y caída >= 15%'
            elif res['pendiente_tendencia'] > 0 and pd.notna(res['cambio_reciente_porcentual']) and res['cambio_reciente_porcentual'] >= 0.15:
                res['clasificacion'] = 'Tendencia creciente'
                res['motivo_clasificacion'] = 'Pendiente positiva y subida >= 15%'
            elif pd.notna(res['coeficiente_variacion']) and res['coeficiente_variacion'] > 0.70:
                res['clasificacion'] = 'Muy variable'
                res['motivo_clasificacion'] = 'CV > 0.70'
            elif pd.notna(res['coeficiente_variacion']) and 0.30 <= res['coeficiente_variacion'] <= 0.70:
                res['clasificacion'] = 'Variable'
                res['motivo_clasificacion'] = '0.30 <= CV <= 0.70'
            else:
                res['clasificacion'] = 'Estable'
                res['motivo_clasificacion'] = 'CV < 0.30 y sin tendencia fuerte'
                
            # Confianza tendencia
            if res['clasificacion'] in ['Tendencia decreciente', 'Tendencia creciente']:
                if meses_disponibles <= 8 or (pd.notna(res['coeficiente_variacion']) and res['coeficiente_variacion'] > 0.70):
                    res['confianza_tendencia'] = 'Baja'
                elif 9 <= meses_disponibles <= 11:
                    res['confianza_tendencia'] = 'Media'
                else: # 12 months
                    diffs = np.diff(sellouts)
                    same_sign = (np.sign(diffs) == np.sign(slope)).sum()
                    if same_sign >= 9:
                        res['confianza_tendencia'] = 'Alta'
                    else:
                        res['confianza_tendencia'] = 'Media'
            
        results.append(res)
        
    out_df = pd.DataFrame(results)
    out_df.to_csv("data/processed/comportamiento_sku.csv", index=False)
    
    print("\n================ RESUMEN DE VALIDACIONES ================")
    print(f"Cantidad total de SKU analizados: {len(out_df)}")
    
    print("\nDistribución por categoría:")
    print(out_df['clasificacion'].value_counts().to_string())
    
    print("\nDistribución por Riesgo Stock:")
    print(out_df['riesgo_stock'].value_counts().to_string())
    
    print("\nDistribución por Confianza de Tendencia:")
    print(out_df['confianza_tendencia'].value_counts().to_string())

if __name__ == "__main__":
    start = time.time()
    compute_metrics()
    print(f"\nTiempo de ejecución: {time.time() - start:.2f} segundos")
