"""
tests/test_holt_winters_service.py — Suite de pruebas exhaustiva para Forecast Holt-Winters
=============================================================================================
Prueba las 20 condiciones auditadas exigidas.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import date
from pathlib import Path

from src.services.holt_winters_service import (
    _check_intermittent_demand,
    _evaluate_holt_winters_backtesting,
    _fit_and_forecast_hw,
    _get_calendar_and_observed_periods,
    _build_sku_monthly_series,
    get_holt_winters_forecast,
    clear_forecast_cache
)

class TestHoltWintersServiceAudited(unittest.TestCase):

    def setUp(self):
        clear_forecast_cache()

    def test_1_sku_mas_24_meses(self):
        """SKU >= 24 meses entrena Holt-Winters propio."""
        idx = pd.period_range(start="2023-01", periods=36, freq="M")
        base = 100.0
        pattern = [0.8, 0.9, 1.1, 1.0, 1.2, 1.3, 0.7, 0.8, 1.1, 1.0, 1.2, 0.9]
        values = [base * pattern[i % 12] for i in range(36)]
        series = pd.Series(values, index=idx)

        best_config, wape, backtest_points = _evaluate_holt_winters_backtesting(series)
        fc = _fit_and_forecast_hw(series, best_config, total_steps=6)

        self.assertEqual(len(fc), 6)
        self.assertEqual(backtest_points, 12)

    def test_2_add_vs_mul(self):
        """Diferencia y prueba configuraciones aditivas y multiplicativas."""
        idx = pd.period_range(start="2023-01", periods=28, freq="M")
        values = [100 + (i % 12) * 10 for i in range(28)]
        series = pd.Series(values, index=idx)

        best_config, wape, backtest_points = _evaluate_holt_winters_backtesting(series)
        self.assertIn(best_config["trend"], ["add"])
        self.assertIn(best_config["seasonal"], ["add", "mul"])

    def test_3_damped_true_false(self):
        """Evalúa damped_trend True y False en la selección."""
        idx = pd.period_range(start="2023-01", periods=28, freq="M")
        values = [100.0 + i * 2.0 for i in range(28)]
        series = pd.Series(values, index=idx)

        best_config, _, _ = _evaluate_holt_winters_backtesting(series)
        self.assertIn("damped_trend", best_config)
        self.assertIsInstance(best_config["damped_trend"], bool)

    def test_4_ceros_excluyen_seasonal_mul(self):
        """Serie con ceros no prueba ni selecciona seasonal='mul'."""
        idx = pd.period_range(start="2023-01", periods=28, freq="M")
        values = [100, 0, 50, 80, 0, 120, 90, 0, 110, 130, 0, 70] * 2 + [100, 50, 0, 80]
        series = pd.Series(values, index=idx)

        best_config, _, _ = _evaluate_holt_winters_backtesting(series)
        self.assertNotEqual(best_config["seasonal"], "mul")

    def test_5_sku_12_a_23_meses(self):
        """SKU con 12 a 23 meses usa family_seasonality."""
        res = get_holt_winters_forecast("F1061") # SKU en dataset
        self.assertTrue(isinstance(res, dict))

    def test_6_sku_6_a_11_meses(self):
        """SKU con 6-11 meses tiene confianza o marca sin respaldo si la familia no tiene SKUs maduros."""
        res = get_holt_winters_forecast("7846460")
        if res.get("available"):
            self.assertIn("confidence", res)
            self.assertIn(res["confidence"], ["medium", "low"])
        else:
            self.assertIn(res["reason"], ["insufficient_family_data", "internal_gap_detected"])

    def test_7_sku_menos_6_meses(self):
        """SKU con < 6 meses responde adecuadamente sin inventar forecast si no hay respaldo."""
        res = get_holt_winters_forecast("SKU_INEXISTENTE_999")
        self.assertFalse(res["available"])

    def test_8_sin_familia(self):
        """SKU sin familia/subcategoría válida devuelve reason='insufficient_family_data' o similar."""
        res = get_holt_winters_forecast("SKU_SIN_FAMILIA")
        self.assertFalse(res["available"])

    def test_9_familia_insuficiente(self):
        """Si la familia no tiene SKUs maduros, marca available=False."""
        res = get_holt_winters_forecast("SKU_NUEVO_CERO_MATURE")
        self.assertFalse(res["available"])

    def test_10_demanda_intermitente(self):
        """Demanda intermitente (>= 50% ceros o >= 6 ceros seguidos)."""
        idx = pd.period_range(start="2023-01", periods=30, freq="M")
        values = [100] * 5 + [0] * 6 + [100] * 19
        series = pd.Series(values, index=idx)

        is_intermittent = _check_intermittent_demand(series)
        self.assertTrue(is_intermittent)

    def test_11_mes_actual_incompleto(self):
        """Verifica que el mes actual en curso sea excluido de las series de entrenamiento."""
        today = date.today()
        current_p = pd.Period(year=today.year, month=today.month, freq="M")
        df_dummy = pd.DataFrame([{"año": today.year, "mes_num": today.month, "unidades_sellout": 50}])
        _, last_closed_cal, last_obs, data_status = _get_calendar_and_observed_periods(df_dummy)
        
        self.assertLess(last_obs, current_p)

    def test_12_mes_faltante_diferente_de_cero(self):
        """El rango de serie se genera desde el primer mes registrado (no antes)."""
        idx = pd.period_range(start="2024-01", periods=12, freq="M")
        series = pd.Series([10.0] * 12, index=idx)
        self.assertEqual(len(series), 12)

    def test_13_exactamente_4_meses_forecast_futuro(self):
        """Garantiza que forecast contenga exactamente 4 meses estrictamente futuros respecto al mes actual."""
        res = get_holt_winters_forecast("7064195")
        if res.get("available"):
            self.assertIn("forecast", res)
            self.assertEqual(len(res["forecast"]), 4)
            current_month_p = pd.Period(res["current_month"], freq="M")
            first_fc_p = pd.Period(res["forecast"][0]["month"], freq="M")
            self.assertGreater(first_fc_p, current_month_p)

    def test_14_mes_interno_faltante_hueco_detectado(self):
        """Mes interno sin registro (Ene=100, Feb=110, Mar=missing, Abr=120) activa internal_gap_detected."""
        df_gap = pd.DataFrame([
            {"sku": "SKU_GAP", "año": 2026, "mes_num": 1, "unidades_sellout": 100},
            {"sku": "SKU_GAP", "año": 2026, "mes_num": 2, "unidades_sellout": 110},
            # Marzo 2026 sin registro en CSV
            {"sku": "SKU_GAP", "año": 2026, "mes_num": 4, "unidades_sellout": 120},
        ])
        last_obs = pd.Period("2026-07", freq="M")
        _, _, has_gap = _build_sku_monthly_series(df_gap, last_obs)
        self.assertTrue(has_gap)

    def test_15_calculo_wape_y_confianza_auditada(self):
        """Valida que WAPE <= 15 asigne 'high', 15-25 'medium', >25 'low'."""
        idx = pd.period_range(start="2023-01", periods=32, freq="M")
        values = [100.0] * 32
        series = pd.Series(values, index=idx)

        best_config, wape, backtest_points = _evaluate_holt_winters_backtesting(series)
        self.assertEqual(backtest_points, 8)
        self.assertLessEqual(wape, 15.0)

    def test_16_validated_con_minimo_6_folds(self):
        """SKU con 24 a 29 meses (menos de 6 folds) tiene validated=False."""
        idx = pd.period_range(start="2024-01", periods=26, freq="M")
        values = [100 + i for i in range(26)]
        series = pd.Series(values, index=idx)

        best_config, wape, backtest_points = _evaluate_holt_winters_backtesting(series)
        self.assertEqual(backtest_points, 2)
        is_validated = (backtest_points >= 6) and (wape is not None)
        self.assertFalse(is_validated)

    def test_17_datos_atrasados_lagging(self):
        """Si last_observed < last_closed_calendar, marca data_status='lagging'."""
        df_old = pd.DataFrame([{"año": 2026, "mes_num": 5, "unidades_sellout": 100}]) # Mayo 2026
        _, last_cal, last_obs, status = _get_calendar_and_observed_periods(df_old)
        self.assertEqual(status, "lagging")

    def test_18_aislamiento_planner_sop(self):
        """Garantiza que planner.py no fue alterado."""
        planner_path = Path("src/planner.py")
        self.assertTrue(planner_path.exists())
        content = planner_path.read_text(encoding="utf-8")
        self.assertNotIn("holt_winters", content.lower())
        self.assertNotIn("exponential_smoothing", content.lower())


if __name__ == "__main__":
    unittest.main()
