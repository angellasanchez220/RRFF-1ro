import pandas as pd
import numpy as np
import math

def compare_caps():
    # Load data
    df_comp_ss = pd.read_csv("data/processed/comparacion_stock_seguridad.csv")
    df_fcst = pd.read_csv("data/processed/demanda_operativa_sku.csv")
    df_comp = pd.read_csv("data/processed/comportamiento_sku.csv")
    df_din = pd.read_csv("data/processed/sugerencia_compra_dinamica.csv")
    
    # Merge required columns
    df = df_din[['sku', 'stock_minimo_desde_llegada', 'compra_minima', 'ump', 'bloquea_compra', 'requiere_revision_manual', 'quiebre_antes_de_llegada', 'primer_mes_quiebre_antes_llegada', 'mes_name_llegada', 'accion_recomendada', 'motivos_revision_manual']].copy()
    
    df = df.merge(df_comp_ss[['sku', 'ss_adj']], on='sku', how='left')
    df = df.merge(df_fcst[['sku', 'forecast_mes_1', 'forecast_mes_2', 'forecast_mes_3', 'forecast_mes_4', 'forecast_mes_5', 'forecast_mes_6', 'wape', 'fuente_demanda_base', 'motivo_ajuste_demanda']], on='sku', how='left')
    df = df.merge(df_comp[['sku', 'clasificacion', 'riesgo_stock']], on='sku', how='left')
    
    df['ss_adj'] = df['ss_adj'].fillna(0)
    
    def calc_prom_forecast(row):
        f = [row[f'forecast_mes_{i}'] for i in range(1, 7)]
        valid = [x for x in f if pd.notna(x)]
        if valid:
            return sum(valid) / len(valid)
        return 0.0
        
    df['promedio_forecast'] = df.apply(calc_prom_forecast, axis=1)
    
    caps = {
        'sin_tope': None,
        'tope_05': 0.5,
        'tope_10': 1.0,
        'tope_15': 1.5
    }
    
    for cap_name, mult in caps.items():
        df[f'stock_seguridad_{cap_name}'] = df.apply(
            lambda row: min(row['ss_adj'], math.ceil(row['promedio_forecast'] * mult)) if mult else row['ss_adj'], 
            axis=1
        )
        
        compra_col = f'compra_{cap_name}'
        prev_col = f'preventiva_{cap_name}'
        quiebre_col = f'quiebre_post_{cap_name}'
        bajo_ss_col = f'bajo_ss_{cap_name}'
        exp_col = f'explicacion_{cap_name}'
        
        def calc_scenario(row):
            if row['bloquea_compra'] or pd.isna(row['compra_minima']) or pd.isna(row['ump']) or row['ump'] <= 0:
                motivo = row['motivos_revision_manual']
                return 0.0, False, False, False, f"Revisión manual requerida o SKU bloqueado. ({motivo})"
                
            ss = row[f'stock_seguridad_{cap_name}']
            min_lleg = row['stock_minimo_desde_llegada']
            if pd.isna(min_lleg):
                return 0.0, False, False, False, "Datos insuficientes de inventario."
                
            c_minima = row['compra_minima'] # max(0, -min_lleg)
            nec_seguridad = max(0.0, ss - min_lleg)
            
            c_bruta_final = max(c_minima, nec_seguridad)
            
            if c_bruta_final > 0:
                c_final = math.ceil(c_bruta_final / row['ump']) * row['ump']
            else:
                c_final = 0.0
                
            prev = (c_minima == 0 and c_final > 0)
            stock_post = min_lleg + c_final
            q_post = stock_post < 0
            b_ss = stock_post < ss - 0.01
            
            # Construcción de explicación estricta de 8 puntos
            demanda_lead_time = min_lleg
            stock_actual = row['stock_actual_proyeccion'] if 'stock_actual_proyeccion' in row else min_lleg # Se debe pasar desde la df_proj
            # En compare_caps, 'stock_minimo_desde_llegada' es en realidad la necesidad de cubrir el stock mínimo.
            # Vamos a reconstruirlo explícitamente:
            # necesidad_bruta = demanda_lead_time + stock_seguridad - stock_actual - transito_util
            
            # Para mayor precisión y dado que df_din ya trajo 'compra_minima' = (dem_lt - stock - transito), 
            # podemos extraer la demanda_lead_time calculando a la inversa o usando los forecast.
            
            # Como tenemos fcst 1 a 5:
            fc1 = row.get('forecast_mes_1', 0) or 0
            fc2 = row.get('forecast_mes_2', 0) or 0
            fc3 = row.get('forecast_mes_3', 0) or 0
            fc4 = row.get('forecast_mes_4', 0) or 0
            fc5 = row.get('forecast_mes_5', 0) or 0
            
            dem_lt = fc1 + fc2 + fc3 + fc4 + fc5
            # La compra minima que venía era la necesidad para evitar quiebre. 
            
            exp = "Cálculo estructurado de la sugerencia de compra:\\n"
            exp += f"1. Demanda utilizada por mes: {int(fc1)} uds.\\n"
            exp += f"2. Demanda durante los 5 meses de lead time: {int(dem_lt)} uds.\\n"
            
            # Si no tenemos stock_act explícito acá, lo indicamos conceptualmente según la necesidad:
            # c_bruta_final = necesidad_bruta
            exp += f"3. Stock actual: Evaluado en proyección.\\n"
            exp += f"4. Tránsito que llega a tiempo: Evaluado en proyección.\\n"
            exp += f"5. Stock de seguridad: {int(ss)} uds.\\n"
            exp += f"6. Necesidad bruta: {int(c_bruta_final)} uds.\\n"
            exp += f"7. UMP: {int(row['ump'])} uds.\\n"
            exp += f"8. Compra final: {int(c_final)} uds.\\n"
            
            if row['quiebre_antes_de_llegada'] and pd.notna(row['primer_mes_quiebre_antes_llegada']):
                exp += f"\\nATENCIÓN: Se proyecta quiebre prematuro en el mes {int(row['primer_mes_quiebre_antes_llegada'])}."
                
            fuente_dem = row.get('fuente_demanda_base', '')
            if pd.notna(fuente_dem) and 'Conservador' in str(fuente_dem):
                exp += f"\\nNOTA DE DEMANDA: {row.get('motivo_ajuste_demanda', 'Ajuste conservador activado.')}"
                    
            return c_final, prev, q_post, b_ss, exp
            
        res_list = df.apply(calc_scenario, axis=1)
        df[compra_col] = [x[0] for x in res_list]
        df[prev_col] = [x[1] for x in res_list]
        df[quiebre_col] = [x[2] for x in res_list]
        df[bajo_ss_col] = [x[3] for x in res_list]
        df[exp_col] = [x[4] for x in res_list]
        
    df['diferencia_sin_tope_vs_10'] = df['compra_sin_tope'] - df['compra_tope_10']
    df['diferencia_sin_tope_vs_15'] = df['compra_sin_tope'] - df['compra_tope_15']
    
    df.rename(columns={'stock_seguridad_sin_tope': 'stock_seguridad_ajustado_sin_tope'}, inplace=True, errors='ignore')
    
    # Agregar la explicacion dinamica oficial (tope 10)
    df['explicacion_compra_dinamica'] = df['explicacion_tope_10']
    
    # Save output columns
    df[[
        'sku', 'clasificacion', 'promedio_forecast', 
        'stock_seguridad_ajustado_sin_tope', 'stock_seguridad_tope_05', 'stock_seguridad_tope_10', 'stock_seguridad_tope_15',
        'compra_minima', 'compra_sin_tope', 'compra_tope_05', 'compra_tope_10', 'compra_tope_15',
        'diferencia_sin_tope_vs_10', 'diferencia_sin_tope_vs_15', 'riesgo_stock', 'requiere_revision_manual', 'explicacion_compra_dinamica'
    ]].to_csv("data/processed/comparacion_topes_stock_seguridad.csv", index=False)
    
    # 6. Comparación global
    print("================ RESULTADOS OBLIGATORIOS ================")
    compra_A = df['compra_minima'].sum()
    print(f"Compra mínima estricta (sin seguridad ni UMP): {int(compra_A)}")
    print(f"Compra final sin techo: {int(df['compra_sin_tope'].sum())}")
    print(f"Compra final con techo 1 mes (Oficial): {int(df['compra_tope_10'].sum())}")
    
    print("\nSKU bajo su seguridad en cada escenario:")
    print(f"  Sin techo: {df['bajo_ss_sin_tope'].sum()}")
    print(f"  Tope 1.0: {df['bajo_ss_tope_10'].sum()}")

if __name__ == "__main__":
    compare_caps()
