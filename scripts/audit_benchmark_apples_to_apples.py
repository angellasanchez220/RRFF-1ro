"""
scripts/audit_benchmark_apples_to_apples.py — Auditoría Final Comparativa Apples-to-Apples
========================================================================================
Auditoría rigurosa y estricta entre el Baseline Holt-Winters y el nuevo Motor de Selección
bajo un protocolo 100% idéntico de Rolling Multi-Horizon Backtesting (h+1, h+2, h+3, h+4).
"""

import sys
import logging
import warnings
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

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
    _dispatch_predict,
    MODEL_LABELS,
    clear_forecast_selection_cache
)
from statsmodels.tsa.holtwinters import ExponentialSmoothing

logging.getLogger("holt_winters_service").setLevel(logging.ERROR)
logging.getLogger("forecast_selection_service").setLevel(logging.ERROR)


def _eval_single_sku_apples_to_apples(sku: str, df_so_sku: pd.DataFrame, last_obs: pd.Period):
    series, hist_len, has_gap = _build_sku_monthly_series(df_so_sku, last_obs)
    hw_res = get_holt_winters_forecast(sku)
    sel_res = get_selected_forecast(sku)

    res_item = {
        "sku": sku,
        "hist_len": hist_len,
        "has_gap": has_gap,
        "hw_res": hw_res,
        "sel_res": sel_res,
        "eval_data": None
    }

    if len(series) < 24 or has_gap or _check_intermittent_demand(series):
        return res_item

    values = series.values.astype(float)
    n = len(values)
    if n < 28:
        return res_item

    origins = list(range(24, n - 3))
    if len(origins) == 0:
        return res_item

    hw_errors = {1: [], 2: [], 3: [], 4: []}
    hw_actuals = {1: [], 2: [], 3: [], 4: []}

    sel_errors = {1: [], 2: [], 3: [], 4: []}
    sel_actuals = {1: [], 2: [], 3: [], 4: []}

    sel_method = sel_res.get("method")
    sel_params = sel_res.get("params", {})
    sel_window = sel_res.get("history_window_months")

    cand_spec = {
        "method": sel_method,
        "params": sel_params
    }

    def predict_cand(hist_subset, steps=4):
        if sel_window and len(hist_subset) > sel_window:
            sub_vals = hist_subset[-sel_window:]
        else:
            sub_vals = hist_subset

        preds = _dispatch_predict(cand_spec, sub_vals, steps)
        if preds is None or len(preds) < steps:
            return [max(0.0, float(np.mean(sub_vals[-6:])))] * steps
        return [max(0.0, float(x)) for x in preds]

    for t in origins:
        train_data = values[:t]
        actual_4 = values[t:t+4]
        if len(actual_4) < 4:
            continue

        # Baseline HW 4-step forecast
        try:
            model_hw = ExponentialSmoothing(
                train_data,
                trend="add",
                seasonal="add",
                seasonal_periods=12,
                damped_trend=False,
                initialization_method="estimated"
            )
            fit_hw = model_hw.fit(optimized=True)
            pred_hw = [max(0.0, float(x)) for x in fit_hw.forecast(4)]
        except Exception:
            pred_hw = [max(0.0, float(np.mean(train_data[-6:])))] * 4

        # New Engine selected candidate 4-step forecast
        pred_sel = predict_cand(train_data, 4)

        for h in range(4):
            act_v = actual_4[h]
            err_hw = abs(act_v - pred_hw[h])
            err_sel = abs(act_v - pred_sel[h])

            hw_errors[h+1].append(err_hw)
            hw_actuals[h+1].append(act_v)

            sel_errors[h+1].append(err_sel)
            sel_actuals[h+1].append(act_v)

    hw_sku_tot_err = sum([sum(hw_errors[h]) for h in range(1, 5)])
    hw_sku_tot_act = sum([sum(hw_actuals[h]) for h in range(1, 5)])
    hw_sku_overall_wape = (hw_sku_tot_err / hw_sku_tot_act * 100.0) if hw_sku_tot_act > 0 else 0.0

    sel_sku_tot_err = sum([sum(sel_errors[h]) for h in range(1, 5)])
    sel_sku_tot_act = sum([sum(sel_actuals[h]) for h in range(1, 5)])
    sel_sku_overall_wape = (sel_sku_tot_err / sel_sku_tot_act * 100.0) if sel_sku_tot_act > 0 else 0.0

    res_item["eval_data"] = {
        "sku": sku,
        "hist_len": n,
        "origins": len(origins),
        "hw_wape": hw_sku_overall_wape,
        "sel_wape": sel_sku_overall_wape,
        "diff_pp": sel_sku_overall_wape - hw_sku_overall_wape,
        "sel_method": sel_method,
        "sel_label": sel_res.get("model_label", MODEL_LABELS.get(sel_method, sel_method)),
        "sel_window": sel_window if sel_window is not None else "full",
        "hw_errors": hw_errors,
        "hw_actuals": hw_actuals,
        "sel_errors": sel_errors,
        "sel_actuals": sel_actuals,
    }

    return res_item


def evaluate_apples_to_apples():
    print("================================================================================", flush=True)
    print("AUDITORÍA FINAL COMPARTIVA APPLES-TO-APPLES: BASELINE HW VS NUEVO MOTOR", flush=True)
    print("================================================================================", flush=True)

    clear_forecast_cache()
    clear_forecast_selection_cache()

    df_so = _get_cleaned_sellout_df()
    if df_so.empty:
        print("ERROR: No se encontró sellout_historico_clean.csv.")
        return

    curr_period, last_closed, last_obs, data_status = _get_calendar_and_observed_periods(df_so)
    all_skus = sorted(df_so["sku"].unique())
    print(f"Catalog Total SKUs: {len(all_skus)}\n", flush=True)

    workers = min(os.cpu_count() or 4, 8)
    print(f"Ejecutando evaluación paralela con {workers} trabajadores...", flush=True)

    sku_groups = {sku: df_so[df_so["sku"] == sku] for sku in all_skus}

    completed_count = 0
    all_items = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_eval_single_sku_apples_to_apples, sku, sku_groups[sku], last_obs): sku
            for sku in all_skus
        }
        for future in as_completed(futures):
            completed_count += 1
            if completed_count % 20 == 0 or completed_count == len(all_skus):
                print(f"Progreso auditoría: {completed_count}/{len(all_skus)} SKUs completados...", flush=True)
            res = future.result()
            all_items.append(res)

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

    hw_available_count = 0
    sel_available_count = 0

    eval_results = []
    hw_abs_err_by_h = [0.0, 0.0, 0.0, 0.0]
    sel_abs_err_by_h = [0.0, 0.0, 0.0, 0.0]
    real_sum_by_h = [0.0, 0.0, 0.0, 0.0]

    for item in all_items:
        hw_res = item["hw_res"]
        sel_res = item["sel_res"]

        if hw_res.get("available"):
            hw_available_count += 1
        if sel_res.get("available"):
            sel_available_count += 1

        if sel_res.get("available"):
            if sel_res.get("method") == "family_seasonality":
                coverage_counts["family_seasonality"] += 1
            elif sel_res.get("validated"):
                coverage_counts["validated_auto_selection"] += 1
            else:
                coverage_counts["available_unvalidated"] += 1
        else:
            reason = sel_res.get("reason", "other")
            if reason == "intermittent_demand":
                coverage_counts["intermittent_demand"] += 1
            elif reason == "internal_gap_detected":
                coverage_counts["internal_gap_detected"] += 1
            elif reason == "insufficient_history":
                coverage_counts["insufficient_history"] += 1
            elif reason == "insufficient_family_data":
                coverage_counts["insufficient_family_data"] += 1
            else:
                coverage_counts["other"] += 1

        if item["eval_data"]:
            ev = item["eval_data"]
            eval_results.append(ev)

            hw_errs = ev["hw_errors"]
            hw_acts = ev["hw_actuals"]
            sel_errs = ev["sel_errors"]
            sel_acts = ev["sel_actuals"]

            for h_idx in range(4):
                h = h_idx + 1
                hw_abs_err_by_h[h_idx] += sum(hw_errs[h])
                sel_abs_err_by_h[h_idx] += sum(sel_errs[h])
                real_sum_by_h[h_idx] += sum(hw_acts[h])

    print("\n--------------------------------------------------------------------------------")
    print("1. CLASIFICACIÓN Y COBERTURA DEL CATÁLOGO (178 SKUs)")
    print("--------------------------------------------------------------------------------")
    for cat, count in coverage_counts.items():
        pct = (count / len(all_skus)) * 100.0
        print(f"  * {cat:32s}: {count:3d} SKUs ({pct:5.1f}%)")
    print(f"\n  * Cobertura Disponible Endpoint Antiguo (HW) : {hw_available_count} SKUs")
    print(f"  * Cobertura Disponible Endpoint Nuevo (Motor): {sel_available_count} SKUs")
    print("--------------------------------------------------------------------------------\n")

    df_eval = pd.DataFrame(eval_results)
    if df_eval.empty:
        print("No se registraron SKUs para evaluación apples-to-apples.")
        return

    total_audited = len(df_eval)

    hw_mean_wape = df_eval["hw_wape"].mean()
    sel_mean_wape = df_eval["sel_wape"].mean()
    hw_median_wape = df_eval["hw_wape"].median()
    sel_median_wape = df_eval["sel_wape"].median()

    tot_real_portfolio = sum(real_sum_by_h)
    hw_portfolio_wape = (sum(hw_abs_err_by_h) / tot_real_portfolio * 100.0) if tot_real_portfolio > 0 else 0.0
    sel_portfolio_wape = (sum(sel_abs_err_by_h) / tot_real_portfolio * 100.0) if tot_real_portfolio > 0 else 0.0

    hw_h_portfolio = [(hw_abs_err_by_h[i] / real_sum_by_h[i] * 100.0) if real_sum_by_h[i] > 0 else 0.0 for i in range(4)]
    sel_h_portfolio = [(sel_abs_err_by_h[i] / real_sum_by_h[i] * 100.0) if real_sum_by_h[i] > 0 else 0.0 for i in range(4)]

    improved_df = df_eval[df_eval["sel_wape"] < df_eval["hw_wape"] - 0.1]
    tied_df = df_eval[abs(df_eval["sel_wape"] - df_eval["hw_wape"]) <= 0.1]
    worsened_df = df_eval[df_eval["sel_wape"] > df_eval["hw_wape"] + 0.1]

    print("================================================================================")
    print("RESUMEN GLOBAL DE PERFORMANCE (APPLES-TO-APPLES PROTOCOL)")
    print("================================================================================")
    print(f"SKUs Evaluados con Multi-Horizonte (h+1..h+4) : {total_audited}")
    print(f"WAPE Medio — Baseline Holt-Winters            : {hw_mean_wape:.2f}%")
    print(f"WAPE Medio — Nuevo Motor de Selección         : {sel_mean_wape:.2f}%")
    print(f"  --> Reducción global de error medio        : {hw_mean_wape - sel_mean_wape:+.2f} pp")
    print("--------------------------------------------------------------------------------")
    print(f"WAPE Mediano — Baseline Holt-Winters          : {hw_median_wape:.2f}%")
    print(f"WAPE Mediano — Nuevo Motor de Selección       : {sel_median_wape:.2f}%")
    print(f"  --> Reducción global de error mediano      : {hw_median_wape - sel_median_wape:+.2f} pp")
    print("--------------------------------------------------------------------------------")
    print(f"Portfolio WAPE (Ponderado por Volumen Real)   :")
    print(f"  * Baseline Holt-Winters Portfolio WAPE      : {hw_portfolio_wape:.2f}%")
    print(f"  * Nuevo Motor de Selección Portfolio WAPE   : {sel_portfolio_wape:.2f}%")
    print(f"  --> Mejora global en volumen de portfolio  : {hw_portfolio_wape - sel_portfolio_wape:+.2f} pp")
    print("================================================================================\n")

    print("--------------------------------------------------------------------------------")
    print("DESGLOSE DE WAPE POR HORIZONTE DE PREDICCIÓN (h+1 a h+4)")
    print("--------------------------------------------------------------------------------")
    print(f"Horizonte      Baseline HW WAPE    Nuevo Motor WAPE    Diferencia (pp)")
    print(f"h+1            {hw_h_portfolio[0]:15.2f}%    {sel_h_portfolio[0]:15.2f}%    {hw_h_portfolio[0] - sel_h_portfolio[0]:+14.2f} pp")
    print(f"h+2            {hw_h_portfolio[1]:15.2f}%    {sel_h_portfolio[1]:15.2f}%    {hw_h_portfolio[1] - sel_h_portfolio[1]:+14.2f} pp")
    print(f"h+3            {hw_h_portfolio[2]:15.2f}%    {sel_h_portfolio[2]:15.2f}%    {hw_h_portfolio[2] - sel_h_portfolio[2]:+14.2f} pp")
    print(f"h+4            {hw_h_portfolio[3]:15.2f}%    {sel_h_portfolio[3]:15.2f}%    {hw_h_portfolio[3] - sel_h_portfolio[3]:+14.2f} pp")
    print(f"Overall (h1-4) {hw_portfolio_wape:15.2f}%    {sel_portfolio_wape:15.2f}%    {hw_portfolio_wape - sel_portfolio_wape:+14.2f} pp")
    print("--------------------------------------------------------------------------------\n")

    print("--------------------------------------------------------------------------------")
    print("DISTRIBUCIÓN DE COMPARACIÓN SKU POR SKU")
    print("--------------------------------------------------------------------------------")
    print(f"SKUs donde Nuevo Motor MEJORA el WAPE : {len(improved_df)} ({len(improved_df)/total_audited*100:.1f}%)")
    print(f"SKUs donde EMPATAN en desempeño       : {len(tied_df)} ({len(tied_df)/total_audited*100:.1f}%)")
    print(f"SKUs donde Baseline HW era superior    : {len(worsened_df)} ({len(worsened_df)/total_audited*100:.1f}%)")
    print("--------------------------------------------------------------------------------\n")

    deg_le_1 = worsened_df[worsened_df["diff_pp"] <= 1.0]
    deg_1_to_5 = worsened_df[(worsened_df["diff_pp"] > 1.0) & (worsened_df["diff_pp"] <= 5.0)]
    deg_gt_5 = worsened_df[worsened_df["diff_pp"] > 5.0]

    print("================================================================================")
    print(f"AUDITORÍA DE LOS {len(worsened_df)} SKUS DONDE BASELINE HOLT-WINTERS FUE SUPERIOR")
    print("================================================================================")
    print(f"  * Degradación <= 1.0 pp (Regla de Tolerancia de Simplicidad) : {len(deg_le_1)} SKUs")
    print(f"  * Degradación > 1.0 pp y <= 5.0 pp                          : {len(deg_1_to_5)} SKUs")
    print(f"  * Degradación > 5.0 pp                                        : {len(deg_gt_5)} SKUs\n")

    print(f"{'SKU':<12} | {'WAPE Base':<10} | {'WAPE Nuevo':<10} | {'Delta (pp)':<10} | {'Modelo Seleccionado':<22} | {'Ventana':<8}")
    print("-" * 85)
    for _, r in worsened_df.sort_values(by="diff_pp", ascending=False).iterrows():
        w_str = str(r["sel_window"]) if r["sel_window"] is not None else "full"
        print(f"{r['sku']:<12} | {r['hw_wape']:9.2f}% | {r['sel_wape']:9.2f}% | {r['diff_pp']:+9.2f} pp | {r['sel_label']:<22} | {w_str:<8}")
    print("================================================================================\n")


if __name__ == "__main__":
    evaluate_apples_to_apples()
