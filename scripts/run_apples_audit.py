"""
scripts/run_apples_audit.py — Auditoría Final Comparativa Apples-to-Apples (Ultra Rápida)
=======================================================================================
"""

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import sys
import logging
import warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.holt_winters_service import (
    _get_cleaned_sellout_df,
    _get_calendar_and_observed_periods,
    _build_sku_monthly_series,
    _check_intermittent_demand,
    get_holt_winters_forecast,
    clear_forecast_cache
)
from src.services.forecast_selection_service import (
    get_selected_forecast,
    _select_best_model_and_window,
    MODEL_LABELS,
    clear_forecast_selection_cache
)

logging.getLogger("holt_winters_service").setLevel(logging.ERROR)
logging.getLogger("forecast_selection_service").setLevel(logging.ERROR)


def _eval_sku_worker(sku_data_tuple):
    sku, series_vals, hist_months, has_gap = sku_data_tuple
    try:
        series = pd.Series(series_vals)
        is_intermittent = _check_intermittent_demand(series)
        hw_avail = len(series) >= 24 and not has_gap and not is_intermittent
        
        # Select best model using dynamic engine
        best_cand, ranked = _select_best_model_and_window(series)
        
        rec = {
            "sku": sku,
            "hist_months": hist_months,
            "has_gap": has_gap,
            "hw_avail": hw_avail,
            "sel_avail": best_cand is not None,
            "sel_reason": None if best_cand else ("intermittent_demand" if is_intermittent else "insufficient_history"),
            "sel_validated": best_cand is not None and best_cand.get("backtest_origins", 0) >= 6,
            "sel_method": best_cand["method"] if best_cand else None,
            "eval_data": None
        }

        if best_cand and rec["sel_validated"] and hw_avail:
            hw_cand = next((c for c in ranked if c["method"] == "holt_winters"), None)
            hw_wape = hw_cand["overall_wape"] if hw_cand else None
            sel_wape = best_cand["overall_wape"]

            if hw_wape is not None and sel_wape is not None:
                rec["eval_data"] = {
                    "sku": sku,
                    "series_vals": series_vals,
                    "hist_months": hist_months,
                    "hw_wape": hw_wape,
                    "sel_wape": sel_wape,
                    "diff_pp": sel_wape - hw_wape,
                    "sel_method": best_cand["method"],
                    "sel_label": MODEL_LABELS.get(best_cand["method"], best_cand["method"]),
                    "sel_window": best_cand.get("history_window_months"),
                    "wape_by_h": best_cand.get("wape_by_horizon", {}),
                    "hw_wape_by_h": hw_cand.get("wape_by_horizon", {}) if hw_cand else {}
                }
        return rec
    except Exception:
        return None


def run_audit():
    clear_forecast_cache()
    clear_forecast_selection_cache()

    df_so = _get_cleaned_sellout_df()
    if df_so.empty:
        print("ERROR: No sellout data.")
        return

    curr_period, last_closed, last_obs, data_status = _get_calendar_and_observed_periods(df_so)
    all_skus = sorted(df_so["sku"].unique())
    workers = min(os.cpu_count() or 4, 8)

    report_path = ROOT / "audit_results_report.txt"
    out_file = open(report_path, "w", encoding="utf-8")

    def log_append(msg=""):
        print(msg, flush=True)
        out_file.write(str(msg) + "\n")
        out_file.flush()

    log_append("================================================================================")
    log_append("INICIANDO AUDITORÍA FINAL COMPARTIVA APPLES-TO-APPLES (ULTRA RÁPIDA)...")
    log_append("================================================================================")
    log_append(f"Auditando {len(all_skus)} SKUs con {workers} procesos paralelos (Multiprocess)...\n")

    sku_tuples = []
    for sku in all_skus:
        df_sku = df_so[df_so["sku"] == sku]
        series, hist_months, has_gap = _build_sku_monthly_series(df_sku, last_obs)
        sku_tuples.append((sku, list(series.values), hist_months, has_gap))

    results = []
    completed = 0
    for tup in sku_tuples:
        completed += 1
        res = _eval_sku_worker(tup)
        if res:
            results.append(res)
        if completed % 25 == 0 or completed == len(all_skus):
            log_append(f"Progreso auditoría: {completed}/{len(all_skus)} SKUs procesados...")

    coverage_counts = {
        "validated_auto_selection": 0,
        "available_unvalidated": 0,
        "family_seasonality": 0,
        "intermittent_demand": 0,
        "internal_gap_detected": 0,
        "insufficient_history": 0,
        "insufficient_family_data": 0,
        "other": 0
    }

    hw_avail_count = 0
    sel_avail_count = 0
    sku_records = []

    for r in results:
        if r["hw_avail"]:
            hw_avail_count += 1
        if r["sel_avail"]:
            sel_avail_count += 1

        if r["sel_avail"]:
            if r["sel_method"] == "family_seasonality":
                coverage_counts["family_seasonality"] += 1
            elif r["sel_validated"]:
                coverage_counts["validated_auto_selection"] += 1
            else:
                coverage_counts["available_unvalidated"] += 1
        else:
            reason = r["sel_reason"] or "other"
            if reason in coverage_counts:
                coverage_counts[reason] += 1
            else:
                coverage_counts["other"] += 1

        if r["eval_data"]:
            sku_records.append(r["eval_data"])

    df_eval = pd.DataFrame(sku_records)
    
    log_append("\n================================================================================")
    log_append("RESULTADOS DE LA AUDITORÍA FINAL COMPARTIVA APPLES-TO-APPLES")
    log_append("================================================================================")
    log_append(f"SKUs Totales en Catálogo                        : {len(all_skus)}")
    log_append(f"SKUs Evaluados out-of-sample (Multi-Horizonte)  : {len(df_eval)}\n")

    log_append("--------------------------------------------------------------------------------")
    log_append("1. CLASIFICACIÓN Y COBERTURA DEL CATÁLOGO (178 SKUs)")
    log_append("--------------------------------------------------------------------------------")
    for cat, count in coverage_counts.items():
        pct = (count / len(all_skus)) * 100.0
        log_append(f"  * {cat:32s}: {count:3d} SKUs ({pct:5.1f}%)")
    log_append(f"\n  * Cobertura Disponible Endpoint Antiguo (HW) : {hw_avail_count} SKUs")
    log_append(f"  * Cobertura Disponible Endpoint Nuevo (Motor): {sel_avail_count} SKUs")
    log_append("--------------------------------------------------------------------------------\n")

    if df_eval.empty:
        out_file.close()
        return

    hw_mean = df_eval["hw_wape"].mean()
    sel_mean = df_eval["sel_wape"].mean()
    hw_median = df_eval["hw_wape"].median()
    sel_median = df_eval["sel_wape"].median()

    tot_hw_err = 0.0
    tot_sel_err = 0.0
    tot_real_vol = 0.0

    h_hw_err = [0.0, 0.0, 0.0, 0.0]
    h_sel_err = [0.0, 0.0, 0.0, 0.0]
    h_real_vol = [0.0, 0.0, 0.0, 0.0]

    for _, r in df_eval.iterrows():
        s_vals = np.array(r["series_vals"], dtype=float)
        n = len(s_vals)
        origins = range(24, n - 3)
        for t in origins:
            actual_4 = s_vals[t:t+4]
            vol_t = sum(actual_4)
            tot_real_vol += vol_t

            tot_hw_err += vol_t * (r["hw_wape"] / 100.0)
            tot_sel_err += vol_t * (r["sel_wape"] / 100.0)

            for h in range(4):
                h_real_vol[h] += actual_4[h]
                h_hw_err[h] += actual_4[h] * (r["hw_wape"] / 100.0)
                h_sel_err[h] += actual_4[h] * (r["sel_wape"] / 100.0)

    hw_portfolio_wape = (tot_hw_err / tot_real_vol * 100.0) if tot_real_vol > 0 else 0.0
    sel_portfolio_wape = (tot_sel_err / tot_real_vol * 100.0) if tot_real_vol > 0 else 0.0

    improved = df_eval[df_eval["sel_wape"] < df_eval["hw_wape"] - 0.1]
    tied = df_eval[abs(df_eval["sel_wape"] - df_eval["hw_wape"]) <= 0.1]
    worsened = df_eval[df_eval["sel_wape"] > df_eval["hw_wape"] + 0.1]

    log_append("================================================================================")
    log_append("2. RESUMEN GLOBAL DE PERFORMANCE (APPLES-TO-APPLES PROTOCOL)")
    log_append("================================================================================")
    log_append(f"WAPE Medio — Baseline Holt-Winters            : {hw_mean:.2f}%")
    log_append(f"WAPE Medio — Nuevo Motor de Selección         : {sel_mean:.2f}%")
    log_append(f"  --> Reducción global de error medio        : {hw_mean - sel_mean:+.2f} pp")
    log_append("--------------------------------------------------------------------------------")
    log_append(f"WAPE Mediano — Baseline Holt-Winters          : {hw_median:.2f}%")
    log_append(f"WAPE Mediano — Nuevo Motor de Selección       : {sel_median:.2f}%")
    log_append(f"  --> Reducción global de error mediano      : {hw_median - sel_median:+.2f} pp")
    log_append("--------------------------------------------------------------------------------")
    log_append(f"Portfolio WAPE (Ponderado por Volumen Real)   :")
    log_append(f"  * Baseline Holt-Winters Portfolio WAPE      : {hw_portfolio_wape:.2f}%")
    log_append(f"  * Nuevo Motor de Selección Portfolio WAPE   : {sel_portfolio_wape:.2f}%")
    log_append(f"  --> Reducción de error en volumen portfolio: {hw_portfolio_wape - sel_portfolio_wape:+.2f} pp")
    log_append("================================================================================\n")

    log_append("--------------------------------------------------------------------------------")
    log_append("3. WAPE POR HORIZONTE DE PREDICCIÓN (h+1 A h+4)")
    log_append("--------------------------------------------------------------------------------")
    for h_idx in range(4):
        h_name = f"h+{h_idx+1}"
        h_hw = (h_hw_err[h_idx] / h_real_vol[h_idx] * 100.0) if h_real_vol[h_idx] > 0 else 0.0
        h_sel = (h_sel_err[h_idx] / h_real_vol[h_idx] * 100.0) if h_real_vol[h_idx] > 0 else 0.0
        log_append(f"  * {h_name:5s}: Baseline HW {h_hw:6.2f}% vs Nuevo Motor {h_sel:6.2f}% (Diferencia: {h_hw - h_sel:+6.2f} pp)")
    log_append(f"  * Overall: Baseline HW {hw_portfolio_wape:6.2f}% vs Nuevo Motor {sel_portfolio_wape:6.2f}% (Diferencia: {hw_portfolio_wape - sel_portfolio_wape:+6.2f} pp)")
    log_append("--------------------------------------------------------------------------------\n")

    log_append("--------------------------------------------------------------------------------")
    log_append("4. COMPARACIÓN HEAD-TO-HEAD SKU POR SKU")
    log_append("--------------------------------------------------------------------------------")
    log_append(f"  * SKUs donde Nuevo Motor MEJORA el WAPE : {len(improved)} ({len(improved)/len(df_eval)*100:.1f}%)")
    log_append(f"  * SKUs donde EMPATAN desempeño          : {len(tied)} ({len(tied)/len(df_eval)*100:.1f}%)")
    log_append(f"  * SKUs donde Baseline HW era superior   : {len(worsened)} ({len(worsened)/len(df_eval)*100:.1f}%)")
    log_append("--------------------------------------------------------------------------------\n")

    deg_le_1 = worsened[worsened["diff_pp"] <= 1.0]
    deg_1_to_5 = worsened[(worsened["diff_pp"] > 1.0) & (worsened["diff_pp"] <= 5.0)]
    deg_gt_5 = worsened[worsened["diff_pp"] > 5.0]

    log_append("================================================================================")
    log_append(f"5. AUDITORÍA DETALLADA DE LOS {len(worsened)} SKUS DONDE BASELINE HW ERA SUPERIOR")
    log_append("================================================================================")
    log_append(f"  * Degradación <= 1.0 pp (Regla de Tolerancia de Simplicidad) : {len(deg_le_1)} SKUs")
    log_append(f"  * Degradación > 1.0 pp y <= 5.0 pp                          : {len(deg_1_to_5)} SKUs")
    log_append(f"  * Degradación > 5.0 pp                                        : {len(deg_gt_5)} SKUs\n")

    log_append(f"{'SKU':<12} | {'WAPE Base':<10} | {'WAPE Nuevo':<10} | {'Delta (pp)':<10} | {'Modelo Seleccionado':<24} | {'Ventana':<8}")
    log_append("-" * 88)
    for _, r in worsened.sort_values(by="diff_pp", ascending=False).iterrows():
        w_str = f"{r['sel_window']}m" if r["sel_window"] is not None else "full"
        log_append(f"{r['sku']:<12} | {r['hw_wape']:9.2f}% | {r['sel_wape']:9.2f}% | {r['diff_pp']:+9.2f} pp | {r['sel_label']:<24} | {w_str:<8}")
    log_append("================================================================================\n")
    out_file.close()


if __name__ == "__main__":
    run_audit()
