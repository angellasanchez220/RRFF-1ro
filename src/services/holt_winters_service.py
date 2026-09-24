"""
src/services/holt_winters_service.py — Forecast de Sell Out (Holt-Winters & Estacionalidad de Familia)
========================================================================================================
Funcionalidad 100% independiente para la proyección analítica de Sell Out.
NO modifica ni influye en:
  - Ritmo consolidado
  - Sugerencia de compra
  - Duración de stock
  - Stock tienda / CD
  - Alertas S&OP
  - Cálculos de planner.py

REGLAS AUDITADAS Y FINALIZADAS:
  1. Forecast estrictamente de 4 meses FUTUROS respecto al mes actual calendario (ej: Oct 2026 - Ene 2027 para hoy Sept 2026).
  2. Los meses de desfase de datos (last_observed < current_month) se calculan e incluyen en `gap_estimates`.
  3. Detección de huecos internos no aclarados (internal gaps): si falta un mes entre el inicio y fin activo, se reporta `reason: "internal_gap_detected"`.
  4. Mejorado el fallback de familia: busca soporte colectivo (>= 2 SKUs maduros) evaluando subcategoria -> categoria -> subfamilia.
  5. Confianza auditada por WAPE (<=15 high, 15-25 medium, >25 low).
"""

import logging
import math
import warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
from sqlalchemy import text
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

log = logging.getLogger("holt_winters_service")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROC_DIR = BASE_DIR / "data" / "processed"

MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

_FORECAST_CACHE = {}


def clear_forecast_cache():
    """Limpia el caché en memoria de forecast."""
    global _FORECAST_CACHE
    _FORECAST_CACHE.clear()


_CLEANED_SELLOUT_DF_CACHE = None


def _get_cleaned_sellout_df() -> pd.DataFrame:
    """Lee sellout_historico_clean.csv y estandariza columnas."""
    global _CLEANED_SELLOUT_DF_CACHE
    if _CLEANED_SELLOUT_DF_CACHE is not None:
        return _CLEANED_SELLOUT_DF_CACHE.copy()

    so_path = PROC_DIR / "sellout_historico_clean.csv"
    if not so_path.exists():
        log.warning("No se encontró sellout_historico_clean.csv en %s", so_path)
        return pd.DataFrame(columns=["sku", "año", "mes", "unidades_sellout"])

    df = pd.read_csv(so_path, sep=";", dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    col_yr = None
    for c in df.columns:
        if c.lower().startswith("a") and c.lower().endswith("o"):
            col_yr = c
            break

    if col_yr:
        df.rename(columns={col_yr: "año"}, inplace=True)

    df["sku"] = df["sku"].astype(str).str.strip()
    df["año"] = pd.to_numeric(df["año"], errors="coerce").fillna(0).astype(int)
    df["mes_str"] = df["mes"].astype(str).str.strip().str.lower()
    df["mes_num"] = df["mes_str"].map(MONTH_MAP).fillna(0).astype(int)
    df["unidades_sellout"] = pd.to_numeric(df["unidades_sellout"], errors="coerce").fillna(0)

    df = df[(df["sku"] != "") & (df["año"] > 2000) & (df["mes_num"] > 0)]
    _CLEANED_SELLOUT_DF_CACHE = df
    return df.copy()


def _get_calendar_and_observed_periods(df: pd.DataFrame) -> tuple[pd.Period, pd.Period, pd.Period, str]:
    """
    Retorna (current_month_period, last_closed_calendar_month, last_observed_month, data_status).
    """
    today = date.today()
    current_period = pd.Period(year=today.year, month=today.month, freq="M")
    last_closed_calendar = current_period - 1

    if df.empty:
        return current_period, last_closed_calendar, last_closed_calendar, "up_to_date"

    df["period"] = df.apply(lambda r: pd.Period(year=r["año"], month=r["mes_num"], freq="M"), axis=1)
    max_data_period = df["period"].max()

    if max_data_period >= current_period:
        last_observed = current_period - 1
    else:
        last_observed = max_data_period

    data_status = "lagging" if last_observed < last_closed_calendar else "up_to_date"
    return current_period, last_closed_calendar, last_observed, data_status


def _build_sku_monthly_series(df_sku: pd.DataFrame, last_observed: pd.Period) -> tuple[pd.Series, int, bool]:
    """
    Construye la serie mensual continua para un SKU hasta last_observed.
    Retorna (series_mensual, cantidad_meses_historicos, has_internal_gap).
    Detecta si existen meses faltantes no registrados dentro de la ventana activa (internal gaps).
    """
    df_sku_closed = df_sku[df_sku.apply(lambda r: pd.Period(year=r["año"], month=r["mes_num"], freq="M") <= last_observed, axis=1)]

    if df_sku_closed.empty:
        return pd.Series(dtype=float), 0, False

    grouped = df_sku_closed.groupby(["año", "mes_num"])["unidades_sellout"].sum().reset_index()
    grouped["period"] = grouped.apply(lambda r: pd.Period(year=r["año"], month=r["mes_num"], freq="M"), axis=1)

    min_period = grouped["period"].min()
    max_recorded = grouped["period"].max()

    # Rango completo activo registrado
    active_recorded_range = pd.period_range(start=min_period, end=max_recorded, freq="M")
    recorded_periods_set = set(grouped["period"].unique())

    # Detectar si hay huecos internos no aclarados entre min_period y max_recorded
    internal_gaps = [p for p in active_recorded_range if p not in recorded_periods_set]
    has_internal_gap = len(internal_gaps) > 0

    full_idx = pd.period_range(start=min_period, end=last_observed, freq="M")
    s_mapped = pd.Series(0.0, index=full_idx)

    for _, row in grouped.iterrows():
        if row["period"] in s_mapped.index:
            s_mapped[row["period"]] = float(row["unidades_sellout"])

    return s_mapped, len(s_mapped), has_internal_gap


def _check_intermittent_demand(series: pd.Series) -> bool:
    """Demanda intermitente: >= 50% ceros o >= 6 ceros consecutivos."""
    if len(series) < 12:
        return False

    zero_ratio = (series == 0).sum() / len(series)
    if zero_ratio >= 0.50:
        return True

    max_zeros = 0
    curr_zeros = 0
    for val in series:
        if val == 0:
            curr_zeros += 1
            if curr_zeros > max_zeros:
                max_zeros = curr_zeros
        else:
            curr_zeros = 0

    return max_zeros >= 6


def _evaluate_holt_winters_backtesting(series: pd.Series) -> tuple[dict, float, int]:
    """Rolling 1-step-ahead backtesting para elegir la mejor configuración."""
    n = len(series)
    min_train = 24
    backtest_points = n - min_train

    candidates = [
        {"trend": "add", "seasonal": "add", "damped_trend": False},
        {"trend": "add", "seasonal": "add", "damped_trend": True},
    ]

    if (series > 0).all():
        candidates.append({"trend": "add", "seasonal": "mul", "damped_trend": False})
        candidates.append({"trend": "add", "seasonal": "mul", "damped_trend": True})

    best_config = candidates[0]
    best_wape = float("inf")

    if backtest_points <= 0:
        return candidates[0], None, 0

    errors_per_cand = {i: [] for i in range(len(candidates))}
    actuals_per_cand = {i: [] for i in range(len(candidates))}

    values = series.values

    for t in range(min_train, n):
        train_data = values[:t]
        actual_val = values[t]

        for i, cand in enumerate(candidates):
            try:
                model = ExponentialSmoothing(
                    train_data,
                    trend=cand["trend"],
                    seasonal=cand["seasonal"],
                    seasonal_periods=12,
                    damped_trend=cand["damped_trend"],
                    initialization_method="estimated"
                )
                fit = model.fit(optimized=True)
                pred = max(0.0, float(fit.forecast(1)[0]))
                
                errors_per_cand[i].append(abs(actual_val - pred))
                actuals_per_cand[i].append(actual_val)
            except Exception:
                errors_per_cand[i].append(abs(actual_val - 0))
                actuals_per_cand[i].append(actual_val)

    for i, cand in enumerate(candidates):
        errs = errors_per_cand[i]
        acts = actuals_per_cand[i]
        sum_act = sum(acts)
        if sum_act > 0:
            wape = (sum(errs) / sum_act) * 100.0
        else:
            wape = float(np.mean(errs)) if errs else 999.0

        if wape < best_wape:
            best_wape = wape
            best_config = cand

    return best_config, best_wape, backtest_points


def _fit_and_forecast_hw(series: pd.Series, config: dict, total_steps: int) -> list[float]:
    """Ajusta modelo final Holt-Winters y predice total_steps hacia adelante."""
    values = series.values
    try:
        model = ExponentialSmoothing(
            values,
            trend=config["trend"],
            seasonal=config["seasonal"],
            seasonal_periods=12,
            damped_trend=config["damped_trend"],
            initialization_method="estimated"
        )
        fit = model.fit(optimized=True)
        raw_fc = fit.forecast(total_steps)
        return [max(0.0, float(x)) for x in raw_fc]
    except Exception as exc:
        log.warning("Fallback de ajuste Holt-Winters con config %s: %s", config, exc)
        mean_val = float(np.mean(values[-6:])) if len(values) >= 6 else float(np.mean(values))
        return [max(0.0, mean_val)] * total_steps


def _get_product_hierarchy_info(sku: str, engine=None) -> dict:
    """Obtiene subcategoria, categoria y subfamilia del SKU."""
    subcat, cat, subfam = "", "", ""
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(
                    text("SELECT subcategoria, categoria, subfamilia FROM dim_productos WHERE sku = :sku LIMIT 1"),
                    {"sku": sku}
                ).fetchone()
                if res:
                    subcat = "" if not res[0] else str(res[0]).strip()
                    cat = "" if not res[1] else str(res[1]).strip()
                    subfam = "" if not res[2] else str(res[2]).strip()
        except Exception as e:
            log.warning("Error consultando dim_productos en DB para SKU %s: %s", sku, e)

    if not subcat and not cat:
        maestro_path = PROC_DIR / "maestro_consolidado.csv"
        if maestro_path.exists():
            try:
                df_m = pd.read_csv(maestro_path, dtype=str)
                row = df_m[df_m["sku"].astype(str).str.strip() == str(sku).strip()]
                if not row.empty:
                    subcat = "" if pd.isna(row.iloc[0].get("subcategoria")) else str(row.iloc[0]["subcategoria"]).strip()
                    cat = "" if pd.isna(row.iloc[0].get("categoria")) else str(row.iloc[0]["categoria"]).strip()
                    subfam = "" if pd.isna(row.iloc[0].get("subfamilia")) else str(row.iloc[0]["subfamilia"]).strip()
            except Exception:
                pass

    return {"subcategoria": subcat, "categoria": cat, "subfamilia": subfam}


def _build_family_seasonality_forecast(
    df_all: pd.DataFrame,
    target_sku: str,
    target_series: pd.Series,
    last_observed: pd.Period,
    total_steps: int,
    engine=None
) -> dict:
    """
    Estacionalidad heredada de familia con MEDIANA y Fallback colectivo mejorado.
    Jerarquía:
      1. Si subcategoría tiene >= 2 SKUs maduros -> usar subcategoría.
      2. Si no, si categoría tiene >= 2 SKUs maduros -> usar categoría.
      3. Si no, si subfamilia tiene >= 2 SKUs maduros -> usar subfamilia.
      4. Si ningún nivel tiene respaldo colectivo (>=2), usar nivel con 1 SKU maduro como referencia individual (is_single_sku_reference=true).
    """
    hier = _get_product_hierarchy_info(target_sku, engine)
    
    def get_skus_in_group(col_name, val):
        if not val:
            return []
        if engine:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(f"SELECT sku FROM dim_productos WHERE {col_name} = :v AND sku != :target"),
                        {"v": val, "target": target_sku}
                    ).fetchall()
                    return [r[0] for r in rows if r[0]]
            except Exception:
                pass
        maestro_path = PROC_DIR / "maestro_consolidado.csv"
        if maestro_path.exists():
            try:
                df_m = pd.read_csv(maestro_path, dtype=str)
                matching = df_m[(df_m[col_name].astype(str).str.strip() == val) & (df_m["sku"].astype(str).str.strip() != target_sku)]
                return matching["sku"].dropna().tolist()
            except Exception:
                pass
        return []

    level_candidates = {}
    for level_name in ["subcategoria", "categoria", "subfamilia"]:
        val = hier.get(level_name)
        if not val:
            continue
        cands = get_skus_in_group(level_name, val)
        mature_list = []
        for s_code in cands:
            df_s = df_all[df_all["sku"] == s_code]
            s_ser, s_len, s_gap = _build_sku_monthly_series(df_s, last_observed)
            if s_len >= 24 and not s_gap and not _check_intermittent_demand(s_ser):
                mature_list.append((s_code, s_ser))
        level_candidates[level_name] = (val, mature_list)

    # Buscar primero respaldo colectivo (>= 2 SKUs maduros)
    selected_level = None
    for level_name in ["subcategoria", "categoria", "subfamilia"]:
        val, mature_list = level_candidates.get(level_name, ("", []))
        if len(mature_list) >= 2:
            selected_level = (level_name, val, mature_list)
            break

    # Si ninguno tiene >= 2, buscar el primero con 1 SKU maduro
    if not selected_level:
        for level_name in ["subcategoria", "categoria", "subfamilia"]:
            val, mature_list = level_candidates.get(level_name, ("", []))
            if len(mature_list) == 1:
                selected_level = (level_name, val, mature_list)
                break

    hist_len = len(target_series)
    if not selected_level:
        return {
            "available": False,
            "sku": target_sku,
            "reason": "insufficient_family_data",
            "historical_months": hist_len
        }

    ref_level, ref_value, mature_skus_info = selected_level
    num_ref_skus = len(mature_skus_info)

    # Matriz de índices estacionales normalizados para cada SKU maduro
    seasonal_factors_matrix = []
    for _, s_ser in mature_skus_info:
        month_means = {}
        for period_idx, val in s_ser.items():
            m_num = period_idx.month
            month_means.setdefault(m_num, []).append(val)

        m_avg = [np.mean(month_means.get(m, [0.0])) for m in range(1, 13)]
        sku_overall_mean = np.mean(m_avg)

        if sku_overall_mean > 0:
            norm_factors = [m_val / sku_overall_mean for m_val in m_avg]
        else:
            norm_factors = [1.0] * 12

        seasonal_factors_matrix.append(norm_factors)

    # MEDIANA mensual
    matrix_np = np.array(seasonal_factors_matrix)
    median_seasonal_pattern = np.median(matrix_np, axis=0)

    pattern_mean = np.mean(median_seasonal_pattern)
    if pattern_mean > 0:
        family_seasonal_index = median_seasonal_pattern / pattern_mean
    else:
        family_seasonal_index = np.array([1.0] * 12)

    # Nivel del SKU objetivo (últimos 6 meses o media disponible)
    if hist_len > 0:
        recent_months = min(6, hist_len)
        target_level = float(np.mean(target_series.values[-recent_months:]))
    else:
        target_level = 0.0

    start_fc_period = last_observed + 1
    forecast_list = []
    for step in range(total_steps):
        fc_period = start_fc_period + step
        m_idx = fc_period.month - 1
        fc_val = max(0.0, target_level * family_seasonal_index[m_idx])
        forecast_list.append(fc_val)

    if hist_len >= 12 and num_ref_skus >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    res_payload = {
        "available": True,
        "sku": target_sku,
        "method": "family_seasonality",
        "historical_months": hist_len,
        "forecast_months": 4,
        "validated": False,
        "wape": None,
        "confidence": confidence,
        "reference_level": ref_level,
        "reference_value": ref_value,
        "reference_skus": num_ref_skus,
        "raw_forecast_all_steps": forecast_list
    }
    if num_ref_skus == 1:
        res_payload["is_single_sku_reference"] = True

    return res_payload


def get_holt_winters_forecast(sku: str, engine=None) -> dict:
    """
    Función principal que retorna el payload del forecast Holt-Winters o Estacionalidad de Familia.
    Garantiza que `forecast` contenga exactamente 4 meses FUTUROS respecto al mes actual calendario.
    """
    sku_clean = str(sku).strip()
    if not sku_clean:
        return {"available": False, "reason": "invalid_sku"}

    df_all = _get_cleaned_sellout_df()
    if df_all.empty:
        return {"available": False, "reason": "no_sellout_data_found"}

    current_month_p, last_closed_calendar, last_observed, data_status = _get_calendar_and_observed_periods(df_all)
    cache_key = (sku_clean, str(last_observed), str(current_month_p), data_status)

    if cache_key in _FORECAST_CACHE:
        return _FORECAST_CACHE[cache_key]

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
        "last_closed_calendar_month": str(last_closed_calendar)
    }

    # Si la serie tiene un hueco interno no aclarado entre min_period y max_recorded:
    if has_internal_gap:
        res = {
            **base_metadata,
            "available": False,
            "sku": sku_clean,
            "reason": "internal_gap_detected",
            "historical_months": hist_months,
            "history": history_records
        }
        _FORECAST_CACHE[cache_key] = res
        return res

    def _period_month_diff(p1: pd.Period, p2: pd.Period) -> int:
        return (p1.year - p2.year) * 12 + (p1.month - p2.month)

    # Pasos totales a predecir = (meses de desfase hasta el mes actual) + 4 meses futuros
    gap_steps = max(0, _period_month_diff(current_month_p, last_observed))
    total_steps = gap_steps + 4

    # Caso A: SKU con >= 24 meses de historial
    if hist_months >= 24:
        if _check_intermittent_demand(series):
            res = {
                **base_metadata,
                "available": False,
                "sku": sku_clean,
                "reason": "intermittent_demand",
                "historical_months": hist_months,
                "history": history_records[-36:] if len(history_records) > 36 else history_records
            }
            _FORECAST_CACHE[cache_key] = res
            return res

        best_config, wape, backtest_points = _evaluate_holt_winters_backtesting(series)
        raw_steps = _fit_and_forecast_hw(series, best_config, total_steps=total_steps)

        is_validated = (backtest_points >= 6) and (wape is not None)
        final_wape = float(round(wape, 1)) if is_validated else None

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

        # Separar gap_estimates (meses <= current_month_p) y forecast (meses estrictamente > current_month_p)
        gap_estimates = [r for r in all_pred_records if pd.Period(r["month"], freq="M") <= current_month_p]
        future_forecast = [r for r in all_pred_records if pd.Period(r["month"], freq="M") > current_month_p][:4]

        res = {
            **base_metadata,
            "available": True,
            "sku": sku_clean,
            "method": "holt_winters",
            "historical_months": hist_months,
            "forecast_months": len(future_forecast),
            "validated": is_validated,
            "backtest_points": backtest_points,
            "wape": final_wape,
            "confidence": confidence,
            "model": {
                "trend": best_config["trend"],
                "seasonal": best_config["seasonal"],
                "damped_trend": best_config["damped_trend"],
                "seasonal_periods": 12
            },
            "history": history_records[-36:] if len(history_records) > 36 else history_records,
            "gap_estimates": gap_estimates,
            "forecast": future_forecast
        }
        _FORECAST_CACHE[cache_key] = res
        return res

    # Caso B: SKU con < 24 meses de historial
    fam_res = _build_family_seasonality_forecast(
        df_all=df_all,
        target_sku=sku_clean,
        target_series=series,
        last_observed=last_observed,
        total_steps=total_steps,
        engine=engine
    )

    if not fam_res.get("available"):
        fam_res.update(base_metadata)
        fam_res["history"] = history_records
        _FORECAST_CACHE[cache_key] = fam_res
        return fam_res

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
    fam_res["history"] = history_records[-36:] if len(history_records) > 36 else history_records
    fam_res["gap_estimates"] = gap_estimates
    fam_res["forecast"] = future_forecast
    fam_res["forecast_months"] = len(future_forecast)

    _FORECAST_CACHE[cache_key] = fam_res
    return fam_res
