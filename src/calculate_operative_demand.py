import pandas as pd
import sqlite3
import numpy as np

def calculate_operative_demand():
    print("Calculando Demanda Base Operativa...")
    
    try:
        df_fcst = pd.read_csv("data/processed/forecast_sku.csv")
    except Exception as e:
        print(f"Error cargando forecast_sku.csv: {e}")
        return
        
    try:
        df_comp = pd.read_csv("data/processed/comportamiento_sku.csv")
        df_hist = pd.read_csv("data/processed/historial_mensual_sku_validado.csv")
    except:
        df_comp = pd.DataFrame()
        df_hist = pd.DataFrame()
        
    # Obtener Legacy igual que en el audit
    try:
        import sys
        sys.path.append('.')
        from api.db import engine
        from api.routes.sop import _get_semanas_fact_ventas
        
        with engine.connect() as conn:
            df_sop = pd.read_sql("SELECT sku, total_4_sem_verificado FROM planificacion_sop", conn)
            sem_map = _get_semanas_fact_ventas(conn)
        
        df_legacy = df_sop.copy()
        for col in ("sem1_uds", "sem2_uds", "sem3_uds", "sem4_uds", "total_4_sem_verificado"):
            df_legacy[col] = df_legacy["sku"].map(lambda s: sem_map.get(s, {}).get(col, 0))
            
        df_legacy["ritmo_semanal_uds"] = df_legacy["total_4_sem_verificado"] / 4.0
        df_legacy["ritmo_mensual_legacy"] = df_legacy["ritmo_semanal_uds"] * 4.33
        
        legacy_dict = df_legacy.set_index('sku')['ritmo_mensual_legacy'].to_dict()
    except Exception as e:
        print(f"Error cargando Legacy DB: {e}")
        legacy_dict = {}

    hist_dict = {}
    if not df_hist.empty:
        for sku, grp in df_hist.groupby('sku'):
            grp = grp.sort_values('fecha_mes', ascending=False).reset_index(drop=True)
            grp = grp[pd.notna(grp['sellout'])]
            if len(grp) >= 3:
                prom_3m = grp.head(3)['sellout'].mean()
            elif len(grp) > 0:
                prom_3m = grp['sellout'].mean()
            else:
                prom_3m = 0
            hist_dict[str(sku)] = prom_3m
            
    comp_dict = df_comp.set_index('sku').to_dict('index') if not df_comp.empty else {}
    
    resultados = []
    
    for _, row in df_fcst.iterrows():
        sku = str(row['sku'])
        
        f1 = float(row.get('forecast_mes_1', 0))
        if pd.isna(f1): f1 = 0
        
        ritmo_mensual = legacy_dict.get(sku, 0)
        prom_3m = hist_dict.get(sku, 0)
        
        # Reglas base
        # Demandas censuradas (historial de quiebres)
        c = comp_dict.get(sku, {})
        pct_quiebre = float(c.get('pct_meses_quiebre', 0))
        demanda_censurada = pct_quiebre > 0.2
        
        # Opciones si se ajusta
        max_valor = max(f1, prom_3m, ritmo_mensual)
        
        # Demanda base por defecto
        demanda_base = f1
        fuente = "Forecast Estadístico"
        motivo = ""
        ajustada = False
        
        if ritmo_mensual > 0 and f1 < ritmo_mensual * 0.6:
            # Existen condiciones para ajustar?
            if demanda_censurada:
                motivo = "No ajustado: dato no confiable (quiebres históricos > 20% censuran demanda real)."
                fuente = "Forecast Estadístico (Con Censura)"
            elif prom_3m == 0:
                motivo = "No ajustado: mes reciente o últimos 3 meses incompletos / sin ventas suficientes."
            else:
                demanda_base = max_valor
                fuente = "Ajuste Conservador (MAX)"
                motivo = f"Ritmo reciente ({ritmo_mensual:.1f}) es significativamente mayor al forecast ({f1:.1f})."
                ajustada = True
                
        # Modificar los meses 1 a 6. Si hubo ajuste, asumimos demanda plana.
        row_out = row.copy()
        
        row_out['promedio_3_meses_completos'] = prom_3m
        row_out['ritmo_mensual_reciente_verificado'] = ritmo_mensual
        row_out['forecast_estadistico_mes_1'] = f1
        row_out['demanda_base_operativa_mes_1'] = demanda_base
        
        if ajustada:
            for i in range(2, 7):
                row_out[f'forecast_mes_{i}'] = demanda_base
                
        row_out['fuente_demanda_base'] = fuente
        row_out['motivo_ajuste'] = motivo
        row_out['demanda_ajustada'] = ajustada
        
        # Conservamos para compatibilidad
        row_out['motivo_ajuste_demanda'] = motivo
        
        if ajustada:
            row_out['forecast_mes_1'] = demanda_base
            
        resultados.append(row_out)
        
    df_out = pd.DataFrame(resultados)
    df_out.to_csv("data/processed/demanda_operativa_sku.csv", index=False)
    print(f"Demanda operativa calculada. {df_out['demanda_ajustada'].sum()} SKUs ajustados.")

if __name__ == "__main__":
    calculate_operative_demand()
