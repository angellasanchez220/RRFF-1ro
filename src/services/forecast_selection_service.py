"""
src/services/forecast_selection_service.py — Motor Autónomo de Selección Dinámica de Forecast
=============================================================================================
Servicio 100% independiente para la selección automática del modelo y ventana histórica de menor
error out-of-sample mediante Rolling Multi-Horizon Backtesting (h+1, h+2, h+3, h+4).

NO MODIFICA NI INFLUYE EN:
  - planner.py
  - transformer.py
  - Sugerencia de compra
  - Ritmo consolidado
  - Ninguna regla S&OP
"""

import logging
import math
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

from src.services.holt_winters_service import (
    _get_cleaned_sellout_df,
    _get_calendar_and_observed_periods,
    _build_sku_monthly_series,
    _check_intermittent_demand,
    _build_family_seasonality_forecast,
)

log = logging.getLogger("forecast_selection_service")
logging.basicConfig(level=logging.INFO)

_FORECAST_SELECTION_CACHE = {}


def clear_forecast_selection_cache():
    """Limpia el caché del motor de selección."""
    global _FORECAST_SELECTION_CACHE
    _FORECAST_SELECTION_CACHE.clear()


# ==============================================================================
# MODEL GENERATORS & PREDICTORS
# ==============================================================================

def _predict_recent_naive(history_vals: np.ndarray, steps: int) -> list[float]:
    if len(history_vals) == 0:
        return [0.0] * steps
    last_val = max(0.0, float(history_vals[-1]))
    return [last_val] * steps


def _predict_seasonal_naive(history_vals: np.ndarray, steps: int) -> list[float] | None:
    if len(history_vals) < 12:
        return None
    preds = []
    for h in range(steps):
        idx = len(history_vals) - 12 + (h % 12)
        val = max(0.0, float(history_vals[idx])) if idx < len(history_vals) else max(0.0, float(history_vals[-1]))
        preds.append(val)
    return preds


def _predict_moving_average(history_vals: np.ndarray, steps: int, window: int) -> list[float] | None:
    if len(history_vals) < window:
        return None
    mean_val = max(0.0, float(np.mean(history_vals[-window:])))
    return [mean_val] * steps


def _predict_weighted_moving_average(history_vals: np.ndarray, steps: int, window: int) -> list[float] | None:
    if len(history_vals) < window:
        return None
    weights = np.arange(1, window + 1, dtype=float)
    recent_vals = history_vals[-window:]
    w_sum = np.sum(weights)
    if w_sum <= 0:
        return None
    wma_val = max(0.0, float(np.sum(recent_vals * weights) / w_sum))
    return [wma_val] * steps


def _predict_recent_trend(history_vals: np.ndarray, steps: int, window: int) -> list[float] | None:
    if len(history_vals) < min(6, window):
        return None
    sub_vals = history_vals[-window:] if len(history_vals) >= window else history_vals
    n = len(sub_vals)
    x = np.arange(n, dtype=float)
    y = np.array(sub_vals, dtype=float)
    
    # Linear regression y = a + b*x
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        slope = 0.0
    else:
        slope = np.sum((x - x_mean) * (y - y_mean)) / denom
    intercept = y_mean - slope * x_mean

    preds = []
    for h in range(1, steps + 1):
        pred_y = intercept + slope * (n - 1 + h)
        preds.append(max(0.0, float(pred_y)))
    return preds


def _predict_holt_ets_non_seasonal(history_vals: np.ndarray, steps: int, damped: bool, fast_mode: bool = False) -> list[float] | None:
    if len(history_vals) < 6:
        return None
    try:
        model = ExponentialSmoothing(
            history_vals,
            trend="add",
            seasonal=None,
            damped_trend=damped,
            initialization_method="heuristic"
        )
        if fast_mode:
            fit = model.fit(smoothing_level=0.3, smoothing_trend=0.1, optimized=False)
        else:
            fit = model.fit(optimized=True, use_brute=False)
        fc = fit.forecast(steps)
        return [max(0.0, float(x)) for x in fc]
    except Exception:
        try:
            model = ExponentialSmoothing(
                history_vals,
                trend=None,
                seasonal=None,
                initialization_method="heuristic"
            )
            if fast_mode:
                fit = model.fit(smoothing_level=0.3, optimized=False)
            else:
                fit = model.fit(optimized=True, use_brute=False)
            fc = fit.forecast(steps)
            return [max(0.0, float(x)) for x in fc]
        except Exception:
            return None


def _predict_holt_winters(history_vals: np.ndarray, steps: int, trend: str, seasonal: str, damped: bool, fast_mode: bool = False) -> list[float] | None:
    if len(history_vals) < 24:
        return None
    if seasonal == "mul" and (history_vals <= 0).any():
        return None
    try:
        model = ExponentialSmoothing(
            history_vals,
            trend=trend,
            seasonal=seasonal,
            seasonal_periods=12,
            damped_trend=damped,
            initialization_method="heuristic"
        )
        if fast_mode:
            fit = model.fit(smoothing_level=0.3, smoothing_trend=0.1, smoothing_seasonal=0.1, optimized=False)
        else:
            fit = model.fit(optimized=True, use_brute=False)
        fc = fit.forecast(steps)
        return [max(0.0, float(x)) for x in fc]
    except Exception:
        return None


def _predict_sarima(history_vals: np.ndarray, steps: int, order: tuple, seasonal_order: tuple) -> list[float] | None:
    if len(history_vals) < 24:
        return None
    try:
        model = SARIMAX(
            history_vals,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        fit = model.fit(disp=False, maxiter=3)
        fc = fit.forecast(steps)
        if np.isnan(fc).any() or np.isinf(fc).any():
            return None
        return [max(0.0, float(x)) for x in fc]
    except Exception:
        return None


# ==============================================================================
# CANDIDATE DEFINITIONS & BACKTESTING ENGINE
# ==============================================================================

COMPLEXITY_MAP = {
    "recent_naive": 1,
    "moving_average": 1,
    "weighted_moving_average": 1,
    "seasonal_naive": 2,
    "recent_trend": 2,
    "holt_ets_non_seasonal": 2,
    "holt_winters": 3,
    "sarima_univariate": 3,
}

MODEL_LABELS = {
    "recent_naive": "Naïve reciente",
    "seasonal_naive": "Seasonal Naïve",
    "moving_average": "Media móvil",
    "weighted_moving_average": "Media móvil ponderada",
    "recent_trend": "Tendencia reciente",
    "holt_ets_non_seasonal": "Holt no estacional",
    "holt_winters": "Holt-Winters",
    "sarima_univariate": "SARIMA",
    "family_seasonality": "Estacionalidad heredada",
}


def _get_candidate_grid() -> list[dict]:
    """Genera la lista de todas las especificaciones de modelos candidato."""
    grid = []

    # 1. Recent Naive
    grid.append({"method": "recent_naive", "params": {}, "min_history": 6})

    # 2. Seasonal Naive
    grid.append({"method": "seasonal_naive", "params": {}, "min_history": 12})

    # 3. Moving Average
    grid.append({"method": "moving_average", "params": {"window": 3}, "min_history": 6})
    grid.append({"method": "moving_average", "params": {"window": 6}, "min_history": 6})

    # 4. Weighted Moving Average
    grid.append({"method": "weighted_moving_average", "params": {"window": 3}, "min_history": 6})
    grid.append({"method": "weighted_moving_average", "params": {"window": 6}, "min_history": 6})

    # 5. Recent Trend
    grid.append({"method": "recent_trend", "params": {"window": 6}, "min_history": 6})
    grid.append({"method": "recent_trend", "params": {"window": 12}, "min_history": 12})
    grid.append({"method": "recent_trend", "params": {"window": 18}, "min_history": 18})

    # 6. Holt ETS Non-Seasonal
    grid.append({"method": "holt_ets_non_seasonal", "params": {"damped": False}, "min_history": 6})
    grid.append({"method": "holt_ets_non_seasonal", "params": {"damped": True}, "min_history": 6})

    # 7. Holt-Winters
    grid.append({"method": "holt_winters", "params": {"trend": "add", "seasonal": "add", "damped": False}, "min_history": 24})
    grid.append({"method": "holt_winters", "params": {"trend": "add", "seasonal": "add", "damped": True}, "min_history": 24})
    grid.append({"method": "holt_winters", "params": {"trend": "add", "seasonal": "mul", "damped": False}, "min_history": 24})
    grid.append({"method": "holt_winters", "params": {"trend": "add", "seasonal": "mul", "damped": True}, "min_history": 24})

    return grid


def _dispatch_predict(cand_spec: dict, train_vals: np.ndarray, steps: int, fast_mode: bool = False) -> list[float] | None:
    method = cand_spec["method"]
    params = cand_spec["params"]

    if method == "recent_naive":
        return _predict_recent_naive(train_vals, steps)
    elif method == "seasonal_naive":
        return _predict_seasonal_naive(train_vals, steps)
    elif method == "moving_average":
        return _predict_moving_average(train_vals, steps, params["window"])
    elif method == "weighted_moving_average":
        return _predict_weighted_moving_average(train_vals, steps, params["window"])
    elif method == "recent_trend":
        return _predict_recent_trend(train_vals, steps, params["window"])
    elif method == "holt_ets_non_seasonal":
        return _predict_holt_ets_non_seasonal(train_vals, steps, params["damped"], fast_mode=fast_mode)
    elif method == "holt_winters":
        return _predict_holt_winters(train_vals, steps, params["trend"], params["seasonal"], params["damped"], fast_mode=fast_mode)
    elif method == "sarima_univariate":
        return _predict_sarima(train_vals, steps, params["order"], params["seasonal_order"])
    return None


def _evaluate_candidate_backtesting(
    cand_spec: dict,
    series_vals: np.ndarray,
    window_months: int | None
) -> dict | None:
    """
    Ejecuta Rolling Multi-Horizon Backtesting (h+1 a h+4) para un candidato y ventana histórica.
    Retorna métricas out-of-sample sin ningún data leakage.
    """
    # 1. Aplicar recorte de ventana histórica si corresponde
    if window_months is not None:
        if len(series_vals) < window_months:
            return None
        sub_series = series_vals[-window_months:]
    else:
        sub_series = series_vals

    n = len(sub_series)
    min_req = cand_spec["min_history"]
    if n < min_req:
        return None

    # Mínimo entrenamiento para iniciar backtesting rolling
    min_train = max(min_req, 12) if cand_spec["method"] in ["holt_winters", "sarima_univariate", "seasonal_naive"] else max(min_req, 6)
    
    if n - min_train < 1:
        # No hay suficientes puntos para hacer al menos 1 fold de backtesting
        return None

    horizon_max = 4
    abs_errors_by_h = {1: [], 2: [], 3: [], 4: []}
    actuals_by_h = {1: [], 2: [], 3: [], 4: []}

    origins_count = 0

    for t in range(min_train, n):
        train_vals = sub_series[:t]
        actuals_ahead = sub_series[t : min(t + horizon_max, n)]
        k_steps = len(actuals_ahead)
        if k_steps < 1:
            break

        preds = _dispatch_predict(cand_spec, train_vals, k_steps, fast_mode=True)
        if preds is None or len(preds) < k_steps:
            return None

        origins_count += 1
        for h_idx in range(k_steps):
            h = h_idx + 1
            act_v = float(actuals_ahead[h_idx])
            pred_v = float(preds[h_idx])
            abs_err = abs(act_v - pred_v)

            abs_errors_by_h[h].append(abs_err)
            actuals_by_h[h].append(act_v)

    if origins_count == 0:
        return None

    # Cálculo de WAPE global y por horizonte
    wape_by_h = {}
    tot_abs_err_all = 0.0
    tot_act_val_all = 0.0

    for h in range(1, 5):
        errs = abs_errors_by_h[h]
        acts = actuals_by_h[h]
        if not errs:
            wape_by_h[f"h{h}"] = None
            continue

        tot_abs_err_all += sum(errs)
        tot_act_val_all += sum(acts)

        sum_act_h = sum(acts)
        if sum_act_h > 0:
            wape_by_h[f"h{h}"] = round((sum(errs) / sum_act_h) * 100.0, 1)
        else:
            wape_by_h[f"h{h}"] = round(float(np.mean(errs)), 1)

    if tot_act_val_all > 0:
        overall_wape = (tot_abs_err_all / tot_act_val_all) * 100.0
    else:
        all_err_flat = [e for h_list in abs_errors_by_h.values() for e in h_list]
        overall_wape = float(np.mean(all_err_flat)) if all_err_flat else 999.0

    overall_wape = round(overall_wape, 1)

    return {
        "candidate": cand_spec,
        "method": cand_spec["method"],
        "model_label": MODEL_LABELS.get(cand_spec["method"], cand_spec["method"]),
        "params": cand_spec["params"],
        "window_months": window_months if window_months is not None else len(series_vals),
        "backtest_origins": origins_count,
        "overall_wape": overall_wape,
        "wape_by_horizon": wape_by_h,
        "complexity": COMPLEXITY_MAP.get(cand_spec["method"], 2)
    }


# ==============================================================================
# SELECTION & TIE-BREAKING LOGIC
# ==============================================================================

def _select_best_model_and_window(series: pd.Series) -> tuple[dict, list[dict]]:
    """
    Evalúa todas las combinaciones Modelo + Ventana y selecciona la óptima
    con criterio de menor WAPE y regla de desempate por simplicidad.
    """
    series_vals = series.values
    cand_grid = _get_candidate_grid()
    window_options = [24, 36, None]  # 24m, 36m y historial completo (full)

    evaluated_results = []

    for cand_spec in cand_grid:
        for w_months in window_options:
            res = _evaluate_candidate_backtesting(cand_spec, series_vals, w_months)
            if res is not None:
                evaluated_results.append(res)

    if not evaluated_results:
        # Fallback por defecto si ninguna evaluación fue posible
        default_res = {
            "candidate": {"method": "recent_naive", "params": {}, "min_history": 6},
            "method": "recent_naive",
            "model_label": MODEL_LABELS["recent_naive"],
            "params": {},
            "window_months": len(series_vals),
            "backtest_origins": 0,
            "overall_wape": 999.0,
            "wape_by_horizon": {"h1": None, "h2": None, "h3": None, "h4": None},
            "complexity": 1
        }
        return default_res, [default_res]

    # Ordenar candidatos por overall_wape ascendente
    evaluated_results.sort(key=lambda x: (x["overall_wape"], x["complexity"]))
    best_wape = evaluated_results[0]["overall_wape"]

    # Aplicar regla de desempate (Complexity Tie-Break):
    # Si existen candidatos con WAPE dentro de 1.0 punto porcentual del mejor, preferir el de menor complejidad.
    tolerance_wape = best_wape + 1.0
    near_top_candidates = [c for c in evaluated_results if c["overall_wape"] <= tolerance_wape]
    near_top_candidates.sort(key=lambda x: (x["complexity"], x["overall_wape"]))

    winning_candidate = near_top_candidates[0]
    return winning_candidate, evaluated_results


# ==============================================================================
# MAIN SERVICE FUNCTION
# ==============================================================================

def get_selected_forecast(sku: str, engine=None) -> dict:
    """
    Función principal del motor dinámico de selección de forecast ("PROYECCIÓN SELL OUT").
    Procesa el SKU, ejecuta la selección de modelos out-of-sample y genera exactamente 4 meses futuros.
    """
    sku_clean = str(sku).strip()
    if not sku_clean:
        return {"available": False, "reason": "invalid_sku"}

    df_all = _get_cleaned_sellout_df()
    if df_all.empty:
        return {"available": False, "reason": "no_sellout_data_found"}

    current_month_p, last_closed_calendar, last_observed, data_status = _get_calendar_and_observed_periods(df_all)
    cache_key = (sku_clean, str(last_observed), str(current_month_p), data_status)

    if cache_key in _FORECAST_SELECTION_CACHE:
        return _FORECAST_SELECTION_CACHE[cache_key]

    df_sku = df_all[df_all["sku"] == sku_clean]
    series, hist_months, has_internal_gap = _build_sku_monthly_series(df_sku, last_observed)

    history_records = []
    for period_idx, val in series.items():
        history_records.append({
            "month": str(period_idx),
            "value": round(float(val), 1)
        })

    base_metadata = {
        "data_status": data_status,
        "current_month": str(current_month_p),
        "last_observed_month": str(last_observed),
        "last_closed_calendar_month": str(last_closed_calendar),
        "historical_months_available": hist_months,
    }

    if hist_months == 0:
        res = {
            **base_metadata,
            "available": False,
            "sku": sku_clean,
            "reason": "no_sellout_data_found",
            "historical_months": 0,
            "history": []
        }
        _FORECAST_SELECTION_CACHE[cache_key] = res
        return res

    # 1. Detección de hueco interno no aclarado
    if has_internal_gap:
        res = {
            **base_metadata,
            "available": False,
            "sku": sku_clean,
            "reason": "internal_gap_detected",
            "historical_months": hist_months,
            "history": history_records
        }
        _FORECAST_SELECTION_CACHE[cache_key] = res
        return res

    def _period_month_diff(p1: pd.Period, p2: pd.Period) -> int:
        return (p1.year - p2.year) * 12 + (p1.month - p2.month)

    gap_steps = max(0, _period_month_diff(current_month_p, last_observed))
    total_steps = gap_steps + 4

    # 2. Detección de demanda intermitente
    if _check_intermittent_demand(series):
        res = {
            **base_metadata,
            "available": False,
            "sku": sku_clean,
            "reason": "intermittent_demand",
            "historical_months": hist_months,
            "history": history_records[-36:] if len(history_records) > 36 else history_records
        }
        _FORECAST_SELECTION_CACHE[cache_key] = res
        return res

    # 3. Caso de SKU joven (<12 meses de historial) -> Fallback a estacionalidad heredada o simple
    if hist_months < 12:
        fam_res = _build_family_seasonality_forecast(
            df_all=df_all,
            target_sku=sku_clean,
            target_series=series,
            last_observed=last_observed,
            total_steps=total_steps,
            engine=engine
        )
        if fam_res.get("available"):
            raw_steps = fam_res.pop("raw_forecast_all_steps", [0.0] * total_steps)
            start_fc_period = last_observed + 1
            all_pred_records = []
            for i, val in enumerate(raw_steps):
                step_period = start_fc_period + i
                all_pred_records.append({
                    "month": str(step_period),
                    "value": round(float(val), 1)
                })

            gap_estimates = [r for r in all_pred_records if pd.Period(r["month"], freq="M") <= current_month_p]
            future_forecast = [r for r in all_pred_records if pd.Period(r["month"], freq="M") > current_month_p][:4]

            fam_res.update(base_metadata)
            fam_res["model_label"] = "Estacionalidad heredada"
            fam_res["history_window_months"] = hist_months
            fam_res["history"] = history_records[-36:] if len(history_records) > 36 else history_records
            fam_res["gap_estimates"] = gap_estimates
            fam_res["forecast"] = future_forecast
            fam_res["forecast_months"] = len(future_forecast)

            _FORECAST_SELECTION_CACHE[cache_key] = fam_res
            return fam_res

    # 4. Caso General (>= 12 meses): Selección dinámica autónoma entre todos los candidatos y ventanas
    winner, all_ranked = _select_best_model_and_window(series)

    # Re-entrenar y predecir con la combinación ganadora sobre la ventana seleccionada
    win_w = winner["window_months"]
    win_series_vals = series.values[-win_w:] if len(series.values) >= win_w else series.values

    raw_steps = _dispatch_predict(winner["candidate"], win_series_vals, total_steps)
    if raw_steps is None or len(raw_steps) < total_steps:
        # Fallback de emergencia si el candidato ganador falla en la predicción final
        raw_steps = _predict_recent_naive(win_series_vals, total_steps)

    raw_steps = [max(0.0, float(x)) for x in raw_steps]

    is_validated = (winner["backtest_origins"] >= 6) and (winner["overall_wape"] < 900.0)
    final_wape = winner["overall_wape"] if is_validated else None

    if is_validated:
        if final_wape <= 15.0:
            confidence = "high"
        elif final_wape <= 25.0:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        confidence = "medium" if hist_months >= 24 else "low"

    start_fc_period = last_observed + 1
    all_pred_records = []
    for i, val in enumerate(raw_steps):
        step_period = start_fc_period + i
        all_pred_records.append({
            "month": str(step_period),
            "value": round(float(val), 1)
        })

    gap_estimates = [r for r in all_pred_records if pd.Period(r["month"], freq="M") <= current_month_p]
    future_forecast = [r for r in all_pred_records if pd.Period(r["month"], freq="M") > current_month_p][:4]

    # Formatear lista diagnóstica de comparación de candidatos
    model_comp_summary = []
    seen_methods = set()
    for item in all_ranked:
        key = (item["method"], item["window_months"])
        if key not in seen_methods:
            seen_methods.add(key)
            model_comp_summary.append({
                "method": item["method"],
                "model_label": item["model_label"],
                "window": item["window_months"],
                "overall_wape": item["overall_wape"],
                "backtest_origins": item["backtest_origins"]
            })

    res = {
        **base_metadata,
        "available": True,
        "sku": sku_clean,
        "method": winner["method"],
        "model_label": winner["model_label"],
        "params": winner["params"],
        "history_window_months": winner["window_months"],
        "historical_months": hist_months,
        "forecast_months": len(future_forecast),
        "validated": is_validated,
        "backtest_origins": winner["backtest_origins"],
        "overall_wape": final_wape,
        "wape_by_horizon": winner["wape_by_horizon"],
        "confidence": confidence,
        "history": history_records[-36:] if len(history_records) > 36 else history_records,
        "gap_estimates": gap_estimates,
        "forecast": future_forecast,
        "model_comparison": model_comp_summary[:10]  # Top 10 diagnósticos
    }

    _FORECAST_SELECTION_CACHE[cache_key] = res
    return res
