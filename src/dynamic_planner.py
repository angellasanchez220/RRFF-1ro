import pandas as pd
import numpy as np
import logging

log = logging.getLogger("planner")

# Importar los scripts analíticos
from src.analyze_sku_behavior import compute_metrics
from src.forecast_sku import calculate_forecast
from src.calculate_operative_demand import calculate_operative_demand
from src.project_inventory import project_inventory
from src.calculate_purchase_suggestion import generate_suggestions
from src.calculate_safety_stock import generate_safety_stock
from src.compare_safety_caps import compare_caps

def run_dynamic_pipeline() -> pd.DataFrame:
    """
    Ejecuta el pipeline predictivo completo y devuelve un DataFrame consolidado
    con las métricas dinámicas requeridas para integrar en el planner.
    """
    log.info("Iniciando pipeline dinámico...")
    
    # 1. Ejecutar en secuencia
    try:
        log.info("Calculando comportamiento...")
        compute_metrics()
        
        log.info("Generando forecast...")
        calculate_forecast()
        
        log.info("Calculando demanda operativa...")
        calculate_operative_demand()
        
        log.info("Proyectando inventario...")
        project_inventory()
        
        log.info("Calculando sugerencia bruta...")
        generate_suggestions()
        
        log.info("Calculando stock de seguridad estadístico...")
        generate_safety_stock()
        
        log.info("Simulando topes de stock de seguridad...")
        compare_caps()
    except Exception as e:
        log.error(f"Error en el pipeline dinámico: {e}")
        return pd.DataFrame() # Retorna vacío si falla
        
    log.info("Pipeline dinámico finalizado con éxito. Consolidando resultados...")
    
    # 2. Leer los CSVs resultantes
    try:
        df_comp = pd.read_csv("data/processed/comportamiento_sku.csv")
        df_fcst = pd.read_csv("data/processed/forecast_sku.csv")
        df_proj = pd.read_csv("data/processed/proyeccion_inventario_sku.csv")
        df_sug = pd.read_csv("data/processed/sugerencia_compra_dinamica.csv")
        df_caps = pd.read_csv("data/processed/comparacion_topes_stock_seguridad.csv")
    except Exception as e:
        log.error(f"Error leyendo CSVs del pipeline dinámico: {e}")
        return pd.DataFrame()
        
    # 3. Consolidar DataFrame final
    # Partimos del maestro de sugerencias (df_sug)
    df_din = df_sug[['sku', 'fecha_estimada_llegada_oc', 'lead_time_meses', 'lead_time_es_provisional', 'fuente_lead_time',
                     'estado_alerta', 'accion_recomendada', 'requiere_revision_manual', 'motivos_revision_manual',
                     'quiebre_antes_de_llegada', 'primer_mes_quiebre_antes_llegada', 'compra_minima']].copy()
                     
    # Renombrar para planner
    df_din.rename(columns={
        'accion_recomendada': 'accion_recomendada_dinamica',
        'requiere_revision_manual': 'requiere_revision_manual_dinamica',
        'motivos_revision_manual': 'motivos_revision_manual_dinamica'
    }, inplace=True)
    
    # Comportamiento
    df_din = df_din.merge(df_comp[['sku', 'clasificacion']], on='sku', how='left')
    df_din.rename(columns={'clasificacion': 'clasificacion_comportamiento'}, inplace=True)
    
    try:
        df_dem = pd.read_csv("data/processed/demanda_operativa_sku.csv")
    except:
        df_dem = df_fcst.copy()
        
    # Forecast
    df_din = df_din.merge(df_fcst[['sku', 'metodo_seleccionado', 'confianza_forecast', 'riesgo_stock']], on='sku', how='left')
    df_din = df_din.merge(df_dem[['sku', 'forecast_mes_1', 'forecast_mes_2', 'forecast_mes_3', 'forecast_mes_4', 'forecast_mes_5', 'forecast_mes_6']], on='sku', how='left')
    df_din.rename(columns={'metodo_seleccionado': 'metodo_forecast'}, inplace=True)
    
    # Proyección (incluyendo tránsitos)
    df_din = df_din.merge(df_proj[['sku', 'stock_fin_mes_1', 'stock_fin_mes_2', 'stock_fin_mes_3', 'stock_fin_mes_4',
                                   'stock_fin_mes_5', 'stock_fin_mes_6',
                                   'transito_confirmado', 'transito_estimado', 'transito_vencido', 'transito_no_calculable',
                                   'cobertura_con_transito_confirmado_meses', 'cobertura_stock_actual_meses',
                                   'primer_mes_quiebre',
                                   'cobertura_proyectada_meses', 'cobertura_menor_5_meses',
                                   'mes_agotamiento_proyectado', 'fecha_limite_compra']], on='sku', how='left')
                                   
    # Caps (Stock Seguridad + Compra Dinámica final con Tope 1.0)
    df_din = df_din.merge(df_caps[['sku', 'stock_seguridad_ajustado_sin_tope', 'stock_seguridad_tope_10', 'compra_tope_10', 'explicacion_compra_dinamica']], on='sku', how='left')
    
    df_din.rename(columns={
        'stock_seguridad_ajustado_sin_tope': 'stock_seguridad_ajustado',
        'stock_seguridad_tope_10': 'stock_seguridad_final',
        'compra_tope_10': 'sugerencia_compra_dinamica'
    }, inplace=True)
    
    df_din['stock_seguridad_tope_meses'] = 1.0
    
    # Convertir sku a string para que el merge posterior sea limpio
    df_din['sku'] = df_din['sku'].astype(str)
    
    log.info(f"Consolidación exitosa: {len(df_din)} SKUs procesados dinámicamente.")
    return df_din

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_dynamic_pipeline()
    if not res.empty:
        print(res.head())

