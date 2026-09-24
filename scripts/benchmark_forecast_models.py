"""
scripts/benchmark_forecast_models.py — Benchmarking Comparativo Masivo de Forecast
====================================================================================
Ejecuta la comparación objetiva entre el forecast Holt-Winters baseline actual y el
nuevo Motor Autónomo de Selección Dinámica sobre todos los SKUs con datos disponibles.

Muestrea el desempeño de WAPE medio, mediano, % de mejora/empate/empeoramiento y
segmenta por madurez (>=24m vs <24m) y SKUs de alta variabilidad (WAPE > 25%).
"""

import sys
import logging
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Añadir la raíz del proyecto al sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.holt_winters_service import (
    _get_cleaned_sellout_df,
    get_holt_winters_forecast,
    clear_forecast_cache
)
from src.services.forecast_selection_service import (
    get_selected_forecast,
    clear_forecast_selection_cache
)

# Silenciar logs verbosos durante el benchmark
logging.getLogger("holt_winters_service").setLevel(logging.ERROR)
logging.getLogger("forecast_selection_service").setLevel(logging.ERROR)


def _eval_sku(sku: str):
    try:
        hw_res = get_holt_winters_forecast(sku)
        sel_res = get_selected_forecast(sku)

        if not hw_res.get("available") and not sel_res.get("available"):
            return None

        hw_wape = hw_res.get("wape")
        sel_wape = sel_res.get("overall_wape")
        hist_months = sel_res.get("historical_months", hw_res.get("historical_months", 0))

        return {
            "sku": sku,
            "hist_months": hist_months,
            "hw_available": hw_res.get("available", False),
            "hw_method": hw_res.get("method", "unavailable"),
            "hw_wape": hw_wape,
            "sel_available": sel_res.get("available", False),
            "sel_method": sel_res.get("method", "unavailable"),
            "sel_model_label": sel_res.get("model_label", "N/A"),
            "sel_window": sel_res.get("history_window_months"),
            "sel_wape": sel_wape,
        }
    except Exception:
        return None


def run_benchmark(max_skus: int = None):
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    print("================================================================================", flush=True)
    print("INICIANDO BENCHMARKING DE MODELOS DE FORECAST: HOLT-WINTERS VS NUEVO MOTOR", flush=True)
    print("================================================================================", flush=True)
    sys.stdout.flush()
    
    clear_forecast_cache()
    clear_forecast_selection_cache()

    df_so = _get_cleaned_sellout_df()
    if df_so.empty:
        print("ERROR: No se encontró sellout_historico_clean.csv para evaluar.", flush=True)
        return

    all_skus = sorted(df_so["sku"].unique())
    if max_skus:
        all_skus = all_skus[:max_skus]

    workers = min(os.cpu_count() or 4, 8)
    print(f"Candidatos totales en catálogo a evaluar: {len(all_skus)} SKUs ({workers} procesos paralelos)\n", flush=True)
    sys.stdout.flush()

    results = []
    completed_count = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_sku = {executor.submit(_eval_sku, sku): sku for sku in all_skus}
        for future in as_completed(future_to_sku):
            completed_count += 1
            if completed_count % 20 == 0 or completed_count == len(all_skus):
                print(f"Progreso: {completed_count}/{len(all_skus)} SKUs procesados...", flush=True)
            res = future.result()
            if res:
                results.append(res)

    print("\n\nEvaluación completada. Generando reporte comparativo...\n")

    df_res = pd.DataFrame(results)
    if df_res.empty:
        print("No se encontraron SKUs válidos con datos suficientes para el benchmark.")
        return

    # Filtrar SKUs que tienen WAPE validado en al menos uno de los métodos
    valid_eval = df_res.dropna(subset=["hw_wape", "sel_wape"])
    
    total_eval = len(valid_eval)
    if total_eval == 0:
        print("No se registraron SKUs con WAPE validado en ambos modelos.")
        return

    hw_mean_wape = valid_eval["hw_wape"].mean()
    sel_mean_wape = valid_eval["sel_wape"].mean()
    hw_median_wape = valid_eval["hw_wape"].median()
    sel_median_wape = valid_eval["sel_wape"].median()

    improved = (valid_eval["sel_wape"] < valid_eval["hw_wape"] - 0.1).sum()
    tied = (abs(valid_eval["sel_wape"] - valid_eval["hw_wape"]) <= 0.1).sum()
    worsened = (valid_eval["sel_wape"] > valid_eval["hw_wape"] + 0.1).sum()

    improved_pct = (improved / total_eval) * 100.0
    tied_pct = (tied / total_eval) * 100.0
    worsened_pct = (worsened / total_eval) * 100.0

    report_lines = []
    report_lines.append("================================================================================")
    report_lines.append("RESUMEN GLOBAL DE PERFORMANCE (BENCHMARK)")
    report_lines.append("================================================================================")
    report_lines.append(f"SKUs auditados y evaluados out-of-sample : {total_eval}")
    report_lines.append(f"WAPE Medio — Holt-Winters Baseline       : {hw_mean_wape:.2f}%")
    report_lines.append(f"WAPE Medio — Nuevo Motor de Selección    : {sel_mean_wape:.2f}%")
    report_lines.append(f"  --> Reducción global de error medio   : {hw_mean_wape - sel_mean_wape:+.2f} pp")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append(f"WAPE Mediano — Holt-Winters Baseline     : {hw_median_wape:.2f}%")
    report_lines.append(f"WAPE Mediano — Nuevo Motor de Selección  : {sel_median_wape:.2f}%")
    report_lines.append(f"  --> Reducción global de error mediano : {hw_median_wape - sel_median_wape:+.2f} pp")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append(f"SKUs donde el Nuevo Motor MEJORA el WAPE : {improved} ({improved_pct:.1f}%)")
    report_lines.append(f"SKUs donde EMPATAN en desempeño          : {tied} ({tied_pct:.1f}%)")
    report_lines.append(f"SKUs donde Holt-Winters era superior     : {worsened} ({worsened_pct:.1f}%)")
    report_lines.append("================================================================================\n")

    # Segmentación A: SKUs Maduros (>= 24 meses)
    maduros = valid_eval[valid_eval["hist_months"] >= 24]
    if not maduros.empty:
        report_lines.append("SEGMENTACIÓN: SKUs MADUROS (>= 24 meses de historial)")
        report_lines.append(f"  * Cantidad evaluada               : {len(maduros)}")
        report_lines.append(f"  * WAPE Medio (HW Baseline vs Nuevo): {maduros['hw_wape'].mean():.2f}% vs {maduros['sel_wape'].mean():.2f}%")
        report_lines.append(f"  * WAPE Mediano                    : {maduros['hw_wape'].median():.2f}% vs {maduros['sel_wape'].median():.2f}%")
        report_lines.append("--------------------------------------------------------------------------------")

    # Segmentación B: SKUs Jóvenes (< 24 meses)
    jovenes = valid_eval[valid_eval["hist_months"] < 24]
    if not jovenes.empty:
        report_lines.append("SEGMENTACIÓN: SKUs JÓVENES (< 24 meses de historial)")
        report_lines.append(f"  * Cantidad evaluada               : {len(jovenes)}")
        report_lines.append(f"  * WAPE Medio (HW Baseline vs Nuevo): {jovenes['hw_wape'].mean():.2f}% vs {jovenes['sel_wape'].mean():.2f}%")
        report_lines.append(f"  * WAPE Mediano                    : {jovenes['hw_wape'].median():.2f}% vs {jovenes['sel_wape'].median():.2f}%")
        report_lines.append("--------------------------------------------------------------------------------")

    # Segmentación C: SKUs con WAPE Holt-Winters > 25% (Alta variabilidad / Difíciles)
    dificiles = valid_eval[valid_eval["hw_wape"] > 25.0]
    if not dificiles.empty:
        report_lines.append("SEGMENTACIÓN: SKUs CON WAPE HOLT-WINTERS > 25% (Alta variabilidad)")
        report_lines.append(f"  * Cantidad evaluada               : {len(dificiles)}")
        report_lines.append(f"  * WAPE Medio (HW Baseline vs Nuevo): {dificiles['hw_wape'].mean():.2f}% vs {dificiles['sel_wape'].mean():.2f}%")
        report_lines.append(f"  * WAPE Mediano                    : {dificiles['hw_wape'].median():.2f}% vs {dificiles['sel_wape'].median():.2f}%")
        report_lines.append(f"  --> Mejora en SKUs difíciles       : {dificiles['hw_wape'].mean() - dificiles['sel_wape'].mean():+.2f} pp")
        report_lines.append("--------------------------------------------------------------------------------")

    # Distribución de modelos ganadores seleccionados por el nuevo motor
    report_lines.append("\nDISTRIBUCIÓN DE MODELOS GANADORES SELECCIONADOS POR EL NUEVO MOTOR:")
    report_lines.append("--------------------------------------------------------------------------------")
    model_counts = valid_eval["sel_model_label"].value_counts()
    for label, count in model_counts.items():
        pct = (count / total_eval) * 100.0
        report_lines.append(f"  * {label:32s}: {count:3d} SKUs ({pct:5.1f}%)")
    report_lines.append("================================================================================\n")

    report_text = "\n".join(report_lines)
    print(report_text, flush=True)

    out_path = ROOT / "data" / "processed" / "benchmark_report.txt"
    try:
        out_path.write_text(report_text, encoding="utf-8")
        print(f"Reporte guardado exitosamente en: {out_path}", flush=True)
    except Exception as e:
        print(f"No se pudo guardar reporte en archivo: {e}", flush=True)


if __name__ == "__main__":
    run_benchmark()
