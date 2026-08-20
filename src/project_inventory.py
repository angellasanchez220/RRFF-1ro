import pandas as pd
import numpy as np
import time

def parse_date(date_str):
    try:
        if pd.isna(date_str) or str(date_str).strip() == '':
            return pd.NaT
        return pd.to_datetime(date_str)
    except:
        return pd.NaT

def _calcular_cobertura_cronologica(stock_inicial, fcst_mensual, transit_mensual):
    cobertura = 0.0
    inv_actual = stock_inicial
    for idx in range(6):
        fc = fcst_mensual[idx]
        tr = transit_mensual[idx]
        inv_disp = inv_actual + tr
        if pd.isna(fc) or fc == 0:
            cobertura += 1.0
            inv_actual = inv_disp
        elif inv_disp >= fc:
            cobertura += 1.0
            inv_actual = inv_disp - fc
        else:
            cobertura += inv_disp / fc
            inv_actual = 0
            break
            
    if cobertura == 6.0 and inv_actual > 0:
        avg_f = np.nanmean([f for f in fcst_mensual if pd.notna(f) and f > 0])
        if pd.notna(avg_f) and avg_f > 0:
            cobertura += inv_actual / avg_f
        else:
            cobertura += 99.0
    return cobertura

def project_inventory():
    print("Cargando datos...")
    df_fcst = pd.read_csv("data/processed/demanda_operativa_sku.csv")
    
    # Load stock
    try:
        df_stock = pd.read_csv("data/processed/inventario_stock_clean.csv", sep=";")
        stock_dict = df_stock.set_index('sku')['stock_act'].to_dict()
    except:
        stock_dict = {}
        
    # Load transit
    try:
        df_trans = pd.read_csv("data/processed/transito_clean.csv", sep=";")
    except:
        df_trans = pd.DataFrame(columns=['sku', 'cantidad_transito', 'fecha_eta', 'fecha_disponibilidad_real'])
        
    # Define today as reference
    today = pd.to_datetime('2026-07-13')
    
    # Months ranges
    m1_start = pd.to_datetime('2026-08-01')
    m1_end = pd.to_datetime('2026-08-31')
    m2_start = pd.to_datetime('2026-09-01')
    m2_end = pd.to_datetime('2026-09-30')
    m3_start = pd.to_datetime('2026-10-01')
    m3_end = pd.to_datetime('2026-10-31')
    m4_start = pd.to_datetime('2026-11-01')
    m4_end = pd.to_datetime('2026-11-30')
    m5_start = pd.to_datetime('2026-12-01')
    m5_end = pd.to_datetime('2026-12-31')
    m6_start = pd.to_datetime('2027-01-01')
    m6_end = pd.to_datetime('2027-01-31')

    # Convert qty to numeric
    df_trans['qty'] = pd.to_numeric(df_trans['cantidad_transito'], errors='coerce').fillna(0)
    
    # Group transit by SKU and category
    trans_summary = {}
    
    for _, row in df_trans.iterrows():
        sku = str(row['sku']).strip()
        if pd.isna(sku) or sku == 'nan': continue
        qty = row['qty']
        
        if sku not in trans_summary:
            trans_summary[sku] = {
                'transito_mes_1': 0, 'transito_mes_2': 0, 'transito_mes_3': 0, 'transito_mes_4': 0,
                'transito_mes_5': 0, 'transito_mes_6': 0,
                'transito_real_mes_1': 0, 'transito_real_mes_2': 0, 'transito_real_mes_3': 0, 'transito_real_mes_4': 0,
                'transito_real_mes_5': 0, 'transito_real_mes_6': 0,
                'transito_fuera_horizonte': 0, 'transito_eta_vencida': 0, 'transito_no_calculable': 0,
                'transito_eta_real': 0, 'transito_eta_estimada': 0,
                'cantidad_embarques_eta_real': 0, 'cantidad_embarques_eta_estimada': 0,
                'cantidad_embarques_eta_vencida': 0, 'cantidad_embarques_no_calculables': 0,
                'eta_utilizada': [], 'tipo_eta': [], 'fecha_base_eta_estimada': []
            }
            
        eta_ajustada = parse_date(row['fecha_disponibilidad_real'])
        eta_original = parse_date(row['fecha_eta'])
        
        # Priority rules
        tipo_eta = ''
        fecha_base = ''
        eta_utilizada = pd.NaT
        es_estimada = False
        
        if pd.notna(eta_ajustada):
            eta_utilizada = eta_ajustada
            tipo_eta = "ETA ajustada"
        elif pd.notna(eta_original):
            eta_utilizada = eta_original
            tipo_eta = "ETA original"
        else:
            fecha_base = "Fecha de ejecución"
            eta_utilizada = today + pd.DateOffset(months=5)
            tipo_eta = "ETA estimada 5 meses"
            es_estimada = True
            
        # Verify if expired
        if pd.notna(eta_utilizada) and eta_utilizada < today:
            tipo_eta = "ETA vencida no confirmada"
            trans_summary[sku]['transito_eta_vencida'] += qty
            trans_summary[sku]['cantidad_embarques_eta_vencida'] += 1
        elif pd.notna(eta_utilizada):
            # Not expired, classify by month
            if es_estimada:
                trans_summary[sku]['transito_eta_estimada'] += qty
                trans_summary[sku]['cantidad_embarques_eta_estimada'] += 1
            else:
                trans_summary[sku]['transito_eta_real'] += qty
                trans_summary[sku]['cantidad_embarques_eta_real'] += 1
                
            if today <= eta_utilizada <= m1_end:
                trans_summary[sku]['transito_mes_1'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_1'] += qty
            elif m2_start <= eta_utilizada <= m2_end:
                trans_summary[sku]['transito_mes_2'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_2'] += qty
            elif m3_start <= eta_utilizada <= m3_end:
                trans_summary[sku]['transito_mes_3'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_3'] += qty
            elif m4_start <= eta_utilizada <= m4_end:
                trans_summary[sku]['transito_mes_4'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_4'] += qty
            elif m5_start <= eta_utilizada <= m5_end:
                trans_summary[sku]['transito_mes_5'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_5'] += qty
            elif m6_start <= eta_utilizada <= m6_end:
                trans_summary[sku]['transito_mes_6'] += qty
                if not es_estimada: trans_summary[sku]['transito_real_mes_6'] += qty
            else:
                trans_summary[sku]['transito_fuera_horizonte'] += qty
        else:
            tipo_eta = "No calculable"
            trans_summary[sku]['transito_no_calculable'] += qty
            trans_summary[sku]['cantidad_embarques_no_calculables'] += 1
            
        trans_summary[sku]['tipo_eta'].append(tipo_eta)
        if pd.notna(eta_utilizada):
            trans_summary[sku]['eta_utilizada'].append(eta_utilizada.strftime("%Y-%m-%d"))
        if fecha_base:
            trans_summary[sku]['fecha_base_eta_estimada'].append(fecha_base)
            
    results = []
    
    for _, row in df_fcst.iterrows():
        sku = str(row['sku']).strip()
        
        # Stock inicial
        stock_inicial_raw = stock_dict.get(sku)
        if pd.isna(stock_inicial_raw):
            stock_inicial = 0.0
            falta_stock = True
        else:
            stock_inicial = float(stock_inicial_raw)
            falta_stock = False
            
        # Transit
        t_data = trans_summary.get(sku, {
            'transito_mes_1': 0, 'transito_mes_2': 0, 'transito_mes_3': 0, 'transito_mes_4': 0,
            'transito_mes_5': 0, 'transito_mes_6': 0,
            'transito_real_mes_1': 0, 'transito_real_mes_2': 0, 'transito_real_mes_3': 0, 'transito_real_mes_4': 0,
            'transito_real_mes_5': 0, 'transito_real_mes_6': 0,
            'transito_fuera_horizonte': 0, 'transito_eta_vencida': 0, 'transito_no_calculable': 0,
            'transito_eta_real': 0, 'transito_eta_estimada': 0,
            'cantidad_embarques_eta_real': 0, 'cantidad_embarques_eta_estimada': 0,
            'cantidad_embarques_eta_vencida': 0, 'cantidad_embarques_no_calculables': 0,
            'eta_utilizada': [], 'tipo_eta': [], 'fecha_base_eta_estimada': []
        })
        
        t1, t2, t3, t4, t5, t6 = t_data['transito_mes_1'], t_data['transito_mes_2'], t_data['transito_mes_3'], t_data['transito_mes_4'], t_data['transito_mes_5'], t_data['transito_mes_6']
        tr1, tr2, tr3, tr4, tr5, tr6 = t_data['transito_real_mes_1'], t_data['transito_real_mes_2'], t_data['transito_real_mes_3'], t_data['transito_real_mes_4'], t_data['transito_real_mes_5'], t_data['transito_real_mes_6']
        
        # Forecasts
        f1 = float(row.get('forecast_mes_1', 0))
        f2 = float(row.get('forecast_mes_2', 0))
        f3 = float(row.get('forecast_mes_3', 0))
        f4 = float(row.get('forecast_mes_4', 0))
        f5 = float(row.get('forecast_mes_5', 0))
        f6 = float(row.get('forecast_mes_6', 0))
        
        quiebre_no_calculable = falta_stock or (pd.isna(f1) and pd.isna(f6))
        
        # Proyecciones con tránsito total incluido cronológicamente
        s1 = stock_inicial + t1 - (f1 if pd.notna(f1) else 0)
        s2 = s1 + t2 - (f2 if pd.notna(f2) else 0)
        s3 = s2 + t3 - (f3 if pd.notna(f3) else 0)
        s4 = s3 + t4 - (f4 if pd.notna(f4) else 0)
        s5 = s4 + t5 - (f5 if pd.notna(f5) else 0)
        s6 = s5 + t6 - (f6 if pd.notna(f6) else 0)
        
        primer_mes = None
        deficit = np.nan
        tiene_quiebre = False
        
        if not quiebre_no_calculable:
            if s1 < 0:
                primer_mes = 1; deficit = s1; tiene_quiebre = True
            elif s2 < 0:
                primer_mes = 2; deficit = s2; tiene_quiebre = True
            elif s3 < 0:
                primer_mes = 3; deficit = s3; tiene_quiebre = True
            elif s4 < 0:
                primer_mes = 4; deficit = s4; tiene_quiebre = True
            elif s5 < 0:
                primer_mes = 5; deficit = s5; tiene_quiebre = True
            elif s6 < 0:
                primer_mes = 6; deficit = s6; tiene_quiebre = True
                
        # Coberturas
        fcst_mensual = [f1, f2, f3, f4, f5, f6]
        cobertura_stock_actual_meses = _calcular_cobertura_cronologica(stock_inicial, fcst_mensual, [0]*6)
        cobertura_con_transito_confirmado_meses = _calcular_cobertura_cronologica(stock_inicial, fcst_mensual, [tr1, tr2, tr3, tr4, tr5, tr6])
        cobertura_proyectada_meses = _calcular_cobertura_cronologica(stock_inicial, fcst_mensual, [t1, t2, t3, t4, t5, t6])
                
        cobertura_menor_5 = (cobertura_proyectada_meses <= 5.0) and not quiebre_no_calculable
        mes_agotamiento_proyectado = primer_mes if tiene_quiebre else None
        
        fecha_limite_compra = pd.NaT
        if tiene_quiebre and primer_mes:
            fecha_limite_compra = today + pd.DateOffset(months=primer_mes-1)
            
        req_rev = row.get('requiere_revision_manual', False)
        motivos = row.get('motivos_revision_manual', '')
        motivos_list = [m.strip() for m in str(motivos).split(';') if m.strip() and m.strip() != 'nan']
        
        if falta_stock:
            req_rev = True
            if "Falta stock actual" not in motivos_list: motivos_list.append("Falta stock actual")
            
        tipos_set = set(t_data['tipo_eta'])
        if "ETA estimada 5 meses" in tipos_set:
            req_rev = True
            motivos_list.append("Tránsito con ETA estimada usando estándar provisional de 5 meses")
        if t_data['fecha_base_eta_estimada'] and "Fecha de ejecución" in set(t_data['fecha_base_eta_estimada']):
            req_rev = True
            motivos_list.append("ETA estimada desde fecha de ejecución")
        if "ETA vencida no confirmada" in tipos_set:
            req_rev = True
            motivos_list.append("Tránsito con ETA vencida pendiente de confirmación")
            
        motivos_final = "; ".join(motivos_list)
        
        out_row = {
            'sku': sku,
            'estado_producto': row.get('estado_producto', ''),
            'bloquea_compra': row.get('bloquea_compra', False),
            'stock_inicial': stock_inicial,
            'falta_stock_actual': falta_stock,
            'forecast_mes_1': f1,
            'forecast_mes_2': f2,
            'forecast_mes_3': f3,
            'forecast_mes_4': f4,
            'forecast_mes_5': f5,
            'forecast_mes_6': f6,
            
            'transito_mes_1': t1,
            'transito_mes_2': t2,
            'transito_mes_3': t3,
            'transito_mes_4': t4,
            'transito_mes_5': t5,
            'transito_mes_6': t6,
            'transito_fuera_horizonte': t_data['transito_fuera_horizonte'],
            
            'lead_time_meses': 5.0,
            'eta_utilizada': " | ".join(sorted(set(t_data['eta_utilizada']))),
            'tipo_eta': " | ".join(sorted(set(t_data['tipo_eta']))),
            'eta_es_estimada': ("ETA estimada 5 meses" in tipos_set),
            'fecha_base_eta_estimada': " | ".join(sorted(set(t_data['fecha_base_eta_estimada']))),
            
            'transito_confirmado': t_data['transito_eta_real'],
            'transito_estimado': t_data['transito_eta_estimada'],
            'transito_vencido': t_data['transito_eta_vencida'],
            'transito_no_calculable': t_data['transito_no_calculable'],
            
            'stock_fin_mes_1': s1,
            'stock_fin_mes_2': s2,
            'stock_fin_mes_3': s3,
            'stock_fin_mes_4': s4,
            'stock_fin_mes_5': s5,
            'stock_fin_mes_6': s6,
            'tiene_quiebre_proyectado': tiene_quiebre,
            'primer_mes_quiebre': primer_mes,
            'deficit_primer_quiebre': deficit,
            'quiebre_no_calculable': quiebre_no_calculable,
            
            'cobertura_stock_actual_meses': cobertura_stock_actual_meses,
            'cobertura_con_transito_confirmado_meses': cobertura_con_transito_confirmado_meses,
            'cobertura_proyectada_meses': cobertura_proyectada_meses,
            'cobertura_menor_5_meses': cobertura_menor_5,
            'mes_agotamiento_proyectado': mes_agotamiento_proyectado,
            'fecha_limite_compra': fecha_limite_compra,
            
            'requiere_revision_manual': req_rev,
            'motivos_revision_manual': motivos_final
        }
        results.append(out_row)
        
    out_df = pd.DataFrame(results)
    out_df.to_csv("data/processed/proyeccion_inventario_sku.csv", index=False)
    print("Project inventory completo.")

if __name__ == "__main__":
    start = time.time()
    project_inventory()
    print(f"\nTiempo de ejecución: {time.time() - start:.2f} segundos")

