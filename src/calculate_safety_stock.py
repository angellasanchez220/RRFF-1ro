import pandas as pd
import numpy as np
import time
import math

def generate_safety_stock():
    print("Cargando datos...")
    df_sug = pd.read_csv("data/processed/sugerencia_compra_dinamica.csv")
    df_comp = pd.read_csv("data/processed/comportamiento_sku.csv")
    df_proj = pd.read_csv("data/processed/proyeccion_inventario_sku.csv")
    
    comp_dict = df_comp.set_index('sku').to_dict('index')
    proj_dict = df_proj.set_index('sku').to_dict('index')
    
    z = 1.65
    lt_meses = 5.0
    sqrt_lt = math.sqrt(lt_meses)
    
    results = []
    
    stats = {
        'total': len(df_sug),
        'con_calculo': 0,
        'sin_calculo': 0,
        'ss_suma': 0.0,
        'ss_max': 0,
        'compra_total_sin': 0,
        'compra_total_con': 0,
        'aumento_cantidad': 0,
        'compra_preventiva_nueva': 0,
        'bloqueados': 0,
        'rev_manual': 0,
        'debajo_ss': 0
    }
    
    for _, row in df_sug.iterrows():
        sku = str(row['sku'])
        estado = row.get('estado_producto', '')
        bloquea = row.get('bloquea_compra', False)
        req_rev = row.get('requiere_revision_manual', False)
        motivos = [m.strip() for m in str(row.get('motivos_revision_manual', '')).split(';') if m.strip()]
        
        comp_info = comp_dict.get(sku, {})
        proj_info = proj_dict.get(sku, {})
        
        std_dev = comp_info.get('desviacion_estandar_venta', np.nan)
        clasificacion = comp_info.get('clasificacion', '')
        riesgo_stock = comp_info.get('riesgo_stock', '')
        posible_limitada = comp_info.get('posible_demanda_limitada_stock', False)
        
        min_desde_llegada = row.get('stock_minimo_desde_llegada', np.nan)
        sug_sin = row.get('compra_minima', np.nan)
        ump = row.get('ump', 1.0)
        
        mes_llegada = row.get('mes_llegada_oc', 6)
        
        # Projections sin compra
        s1 = float(proj_info.get('stock_fin_mes_1', np.nan))
        s2 = float(proj_info.get('stock_fin_mes_2', np.nan))
        s3 = float(proj_info.get('stock_fin_mes_3', np.nan))
        s4 = float(proj_info.get('stock_fin_mes_4', np.nan))
        s5 = float(proj_info.get('stock_fin_mes_5', np.nan))
        s6 = float(proj_info.get('stock_fin_mes_6', np.nan))
        proj = [s1, s2, s3, s4, s5, s6]
        
        res = {
            'sku': sku,
            'estado_producto': estado,
            'clasificacion': clasificacion,
            'riesgo_stock': riesgo_stock,
            'desviacion_estandar_venta': std_dev,
            'nivel_servicio': '95%',
            'factor_z': z,
            'lead_time_meses': lt_meses,
            'stock_seguridad': np.nan,
            'stock_minimo_desde_llegada': min_desde_llegada,
            'sugerencia_sin_seguridad': sug_sin,
            'necesidad_con_seguridad': np.nan,
            'compra_bruta_con_seguridad': np.nan,
            'sugerencia_con_seguridad': np.nan,
            'aumento_por_seguridad': np.nan,
            'aumento_por_seguridad_porcentual': np.nan,
            'compra_nueva_generada_por_seguridad': False,
            'requiere_revision_manual': req_rev,
            'motivos_revision_manual': '',
            'explicacion_stock_seguridad': ''
        }
        
        exp_lines = []
        
        # Casos especiales
        if bloquea or str(estado).lower() in ['descontinuado', 'inactivo', 'bloqueado', 'bloqueados']:
            res['stock_seguridad'] = 0.0
            res['sugerencia_con_seguridad'] = 0.0
            res['necesidad_con_seguridad'] = 0.0
            res['compra_bruta_con_seguridad'] = 0.0
            res['aumento_por_seguridad'] = 0.0
            res['aumento_por_seguridad_porcentual'] = 0.0
            res['explicacion_stock_seguridad'] = "Producto bloqueado o descontinuado."
            stats['bloqueados'] += 1
            stats['sin_calculo'] += 1
            
        elif clasificacion == 'Sin historial suficiente' or pd.isna(std_dev) or pd.isna(min_desde_llegada):
            res['requiere_revision_manual'] = True
            if "Historial insuficiente o falta desviación" not in motivos:
                motivos.append("Historial insuficiente o falta desviación")
            res['explicacion_stock_seguridad'] = "Revisión manual requerida por historial insuficiente."
            stats['rev_manual'] += 1
            stats['sin_calculo'] += 1
            
        elif clasificacion == 'Sin demanda':
            res['stock_seguridad'] = 0.0
            res['sugerencia_con_seguridad'] = 0.0
            res['necesidad_con_seguridad'] = 0.0
            res['compra_bruta_con_seguridad'] = 0.0
            res['aumento_por_seguridad'] = 0.0
            res['aumento_por_seguridad_porcentual'] = 0.0
            res['explicacion_stock_seguridad'] = "Sin demanda histórica, no requiere stock de seguridad."
            stats['con_calculo'] += 1
            
        else:
            # Calcular SS
            ss_bruto = z * std_dev * sqrt_lt
            ss = math.ceil(ss_bruto)
            res['stock_seguridad'] = ss
            
            stats['con_calculo'] += 1
            stats['ss_suma'] += ss
            if ss > stats['ss_max']: stats['ss_max'] = ss
            
            if posible_limitada:
                exp_lines.append("El stock de seguridad puede estar subestimado porque las ventas observadas pudieron estar limitadas por falta de stock.")
                
            # Necesidad con seguridad
            necesidad = max(0.0, ss - min_desde_llegada)
            res['necesidad_con_seguridad'] = necesidad
            
            # Compra bruta y ajuste
            res['compra_bruta_con_seguridad'] = necesidad
            
            if necesidad > 0:
                sug_con = math.ceil(necesidad / ump) * ump
            else:
                sug_con = 0.0
                
            res['sugerencia_con_seguridad'] = sug_con
            
            # Aumentos
            aumento = sug_con - sug_sin
            res['aumento_por_seguridad'] = aumento
            if sug_sin > 0:
                res['aumento_por_seguridad_porcentual'] = aumento / sug_sin
            else:
                res['aumento_por_seguridad_porcentual'] = np.nan
                
            if sug_sin == 0 and sug_con > 0:
                res['compra_nueva_generada_por_seguridad'] = True
                stats['compra_preventiva_nueva'] += 1
                exp_lines.append("Compra preventiva generada para proteger el nivel de servicio.")
            elif aumento > 0:
                stats['aumento_cantidad'] += 1
                exp_lines.append(f"La cantidad aumentó en {aumento} unidades por protección estadística.")
            elif sug_con > 0:
                exp_lines.append("La compra base ya cubría el stock de seguridad requerido (por efecto del lote UMP).")
            else:
                exp_lines.append("El inventario proyectado sin compra es suficiente para cubrir el stock de seguridad.")
                
            res['explicacion_stock_seguridad'] = " ".join(exp_lines)
            
            # Validar si despues de la compra queda por debajo del SS
            # Mes llegada (1-indexed)
            if mes_llegada <= 6:
                sim_proj = proj.copy()
                for i in range(mes_llegada - 1, 6):
                    sim_proj[i] += sug_con
                
                min_despues_ss = np.min(sim_proj[mes_llegada-1:])
                if min_despues_ss < ss - 0.001:
                    stats['debajo_ss'] += 1
            
            if pd.notna(sug_sin): stats['compra_total_sin'] += sug_sin
            if pd.notna(sug_con): stats['compra_total_con'] += sug_con
            
        res['motivos_revision_manual'] = "; ".join(motivos)
        results.append(res)
        
    out_df = pd.DataFrame(results)
    out_df.to_csv("data/processed/sugerencia_compra_con_seguridad.csv", index=False)
    
    # Validaciones
    ss_promedio = stats['ss_suma'] / stats['con_calculo'] if stats['con_calculo'] > 0 else 0
    diferencia_total = stats['compra_total_con'] - stats['compra_total_sin']
    
    print("\n================ RESUMEN DE VALIDACIONES ================")
    print(f"Total SKU: {stats['total']}")
    print(f"SKU con stock de seguridad calculado: {stats['con_calculo']}")
    print(f"SKU sin cálculo: {stats['sin_calculo']}")
    print(f"Stock de seguridad promedio: {ss_promedio:.1f}")
    print(f"Stock de seguridad máximo: {stats['ss_max']}")
    print(f"Compra total sin seguridad: {int(stats['compra_total_sin'])}")
    print(f"Compra total con seguridad: {int(stats['compra_total_con'])}")
    print(f"Diferencia total: +{int(diferencia_total)}")
    
    print(f"SKU que ya compraban y aumentaron cantidad: {stats['aumento_cantidad']}")
    print(f"SKU que no compraban y ahora generan compra preventiva: {stats['compra_preventiva_nueva']}")
    print(f"SKU bloqueados: {stats['bloqueados']}")
    real_rev = out_df['requiere_revision_manual'].sum()
    print(f"SKU en revisión manual (total bandera): {real_rev}")
    print(f"SKU que después de la compra quedan bajo su stock de seguridad: {stats['debajo_ss']}")
    
if __name__ == "__main__":
    start = time.time()
    generate_safety_stock()
    print(f"\nTiempo de ejecución: {time.time() - start:.2f} segundos")
