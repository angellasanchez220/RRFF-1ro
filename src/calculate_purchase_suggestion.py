import pandas as pd
import numpy as np
import time
import math

def generate_suggestions():
    print("Cargando datos...")
    df_proj = pd.read_csv("data/processed/proyeccion_inventario_sku.csv")
    
    # Load UMP from database dim_productos
    try:
        from api.db import engine
        df_maestro = pd.read_sql("SELECT sku, ump, gancheras FROM dim_productos", engine)
        ump_dict = {}
        for _, row in df_maestro.iterrows():
            sku = str(row['sku']).strip()
            g = pd.to_numeric(row.get('ump'), errors='coerce')
            if pd.isna(g) or g <= 0:
                g = pd.to_numeric(row.get('gancheras'), errors='coerce')
            if pd.isna(g) or g <= 0:
                g = 1 
            ump_dict[sku] = g
    except Exception as e:
        print(f"Error loading UMP from DB: {e}")
        ump_dict = {}
        
    today = pd.to_datetime('2026-07-13')
    lt_meses = 5.0
    eta_nueva_oc = today + pd.DateOffset(months=5)
    
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
    
    mes_llegada = 0
    mes_name = "Fuera de horizonte"
    
    if today <= eta_nueva_oc <= m1_end:
        mes_llegada = 1; mes_name = "Agosto"
    elif m2_start <= eta_nueva_oc <= m2_end:
        mes_llegada = 2; mes_name = "Septiembre"
    elif m3_start <= eta_nueva_oc <= m3_end:
        mes_llegada = 3; mes_name = "Octubre"
    elif m4_start <= eta_nueva_oc <= m4_end:
        mes_llegada = 4; mes_name = "Noviembre"
    elif m5_start <= eta_nueva_oc <= m5_end:
        mes_llegada = 5; mes_name = "Diciembre"
    elif m6_start <= eta_nueva_oc <= m6_end:
        mes_llegada = 6; mes_name = "Enero"
    else:
        mes_llegada = 7; mes_name = "Fuera de horizonte"
        
    results = []
    
    stats = {
        'total': len(df_proj),
        'sug_pos': 0,
        'sug_cero': 0,
        'sug_nan': 0,
        'bloqueada': 0,
        'rev_manual': 0,
        'quiebre_antes': 0,
        'brutas': 0,
        'criticos': 0,
        'urgentes': 0,
        'vigilancia': 0,
        'normales': 0
    }
    
    for _, row in df_proj.iterrows():
        sku = str(row['sku'])
        estado = row.get('estado_producto', '')
        bloquea = row.get('bloquea_compra', False)
        falta_stock = row.get('falta_stock_actual', False)
        q_no_calc = row.get('quiebre_no_calculable', False)
        ump_val = ump_dict.get(sku, 0)
        cobertura = float(row.get('cobertura_proyectada_meses', 0))
        
        # Original projections
        s1 = float(row.get('stock_fin_mes_1', np.nan))
        s2 = float(row.get('stock_fin_mes_2', np.nan))
        s3 = float(row.get('stock_fin_mes_3', np.nan))
        s4 = float(row.get('stock_fin_mes_4', np.nan))
        s5 = float(row.get('stock_fin_mes_5', np.nan))
        s6 = float(row.get('stock_fin_mes_6', np.nan))
        
        proj = [s1, s2, s3, s4, s5, s6]
        
        res = {
            'sku': sku,
            'estado_producto': estado,
            'fecha_calculo': today.strftime("%Y-%m-%d"),
            'lead_time_meses': lt_meses,
            'lead_time_es_provisional': True,
            'fuente_lead_time': "Regla de negocio informada: reposición aproximada de 5 meses",
            'fecha_estimada_llegada_oc': eta_nueva_oc.strftime("%Y-%m-%d"),
            'mes_llegada_oc': mes_llegada,
            'mes_name_llegada': mes_name,
            'bloquea_compra': bloquea,
            'compra_automatica_permitida': True,
            'ump': ump_val,
            'stock_inicial': row.get('stock_inicial', np.nan),
            'stock_minimo_desde_llegada': np.nan,
            'compra_minima': np.nan,
            'quiebre_antes_de_llegada': False,
            'primer_mes_quiebre_antes_llegada': np.nan,
            'deficit_antes_de_llegada': np.nan,
            'accion_recomendada': '',
            'estado_alerta': '',
            'requiere_revision_manual': row.get('requiere_revision_manual', False),
            'motivos_revision_manual': row.get('motivos_revision_manual', ''),
        }
        
        motivos = [m.strip() for m in str(res['motivos_revision_manual']).split(';') if m.strip() and m.strip() != 'nan']
        
        if bloquea or str(estado).lower() == 'descontinuado':
            res['compra_automatica_permitida'] = False
            res['accion_recomendada'] = "Compra bloqueada"
            res['estado_alerta'] = "Bloqueado"
            res['compra_minima'] = 0.0
            stats['sug_cero'] += 1
            stats['bloqueada'] += 1
            results.append(res)
            continue
            
        if pd.isna(ump_val) or ump_val <= 0:
            res['compra_automatica_permitida'] = False
            res['requiere_revision_manual'] = True
            if "Falta UMP válida" not in motivos: motivos.append("Falta UMP válida")
            
        if q_no_calc or falta_stock:
            res['compra_automatica_permitida'] = False
            res['requiere_revision_manual'] = True
            
        if mes_llegada > 6:
            res['compra_automatica_permitida'] = False
            res['requiere_revision_manual'] = True
            if "OC llegaría fuera de horizonte" not in motivos: motivos.append("OC llegaría fuera de horizonte")
            
        if not res['compra_automatica_permitida']:
            res['motivos_revision_manual'] = "; ".join(motivos)
            res['accion_recomendada'] = "Revisión manual"
            res['estado_alerta'] = "Revisión manual"
            res['compra_minima'] = np.nan
            stats['sug_nan'] += 1
            stats['rev_manual'] += 1
            results.append(res)
            continue
            
        # 3. Detect deficits before arrival
        q_antes = False
        p_mes = None
        def_antes = np.nan
        for i in range(mes_llegada - 1): # If arrival is mes 5, we check mes 1 to 4
            if proj[i] < 0:
                q_antes = True
                p_mes = i + 1
                def_antes = proj[i]
                break
                
        res['quiebre_antes_de_llegada'] = q_antes
        if q_antes:
            res['primer_mes_quiebre_antes_llegada'] = p_mes
            res['deficit_antes_de_llegada'] = def_antes
            stats['quiebre_antes'] += 1
            if "Existe déficit antes de que una nueva OC pueda llegar; requiere acción logística inmediata" not in motivos:
                motivos.append("Existe déficit antes de que una nueva OC pueda llegar; requiere acción logística inmediata")
                
        # 4. Requirements from arrival month (compra minima para no quebrar)
        min_desde_llegada = np.min(proj[mes_llegada-1:])
        res['stock_minimo_desde_llegada'] = min_desde_llegada
        
        c_minima = max(0.0, -min_desde_llegada)
        res['compra_minima'] = c_minima
        stats['brutas'] += c_minima
        if c_minima > 0: stats['sug_pos'] += 1
        else: stats['sug_cero'] += 1
        
        # 7. Action and Alerts (Preliminary)
        if q_antes:
            res['estado_alerta'] = "Urgente"
            stats['urgentes'] += 1
        elif cobertura <= 5.0:
            res['estado_alerta'] = "Crítico"
            stats['criticos'] += 1
        elif 5.0 < cobertura <= 6.0:
            res['estado_alerta'] = "Vigilancia"
            stats['vigilancia'] += 1
        else:
            res['estado_alerta'] = "Normal"
            stats['normales'] += 1
            
        if res['quiebre_antes_de_llegada'] and c_minima > 0:
            res['accion_recomendada'] = "Compra urgente, pero no llega a tiempo"
        elif c_minima > 0 and not res['quiebre_antes_de_llegada']:
            res['accion_recomendada'] = "Comprar"
        elif c_minima == 0:
            res['accion_recomendada'] = "No comprar"
            
        res['motivos_revision_manual'] = "; ".join(motivos)
        results.append(res)
        
    out_df = pd.DataFrame(results)
    out_df.to_csv("data/processed/sugerencia_compra_dinamica.csv", index=False)
    
    print("\n================ RESUMEN DE ESTADOS ================")
    print(f"Urgente: {stats['urgentes']}")
    print(f"Crítico: {stats['criticos']}")
    print(f"Vigilancia: {stats['vigilancia']}")
    print(f"Normal: {stats['normales']}")
    print(f"Revisión manual: {stats['rev_manual']}")
    print(f"Bloqueado: {stats['bloqueada']}")
    
if __name__ == "__main__":
    start = time.time()
    generate_suggestions()
    print(f"\nTiempo de ejecución: {time.time() - start:.2f} segundos")
