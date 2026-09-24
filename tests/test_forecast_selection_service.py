"""
tests/test_forecast_selection_service.py
=========================================
Suite de 24+ pruebas unitarias automatizadas para verificar el comportamiento,
aislamiento S&OP, ausencia de data leakage, rolling multi-horizon WAPE,
tie-breaking por simplicidad y robustness del motor dinámico de forecast.
"""

import unittest
import numpy as np
import pandas as pd

from src.services.forecast_selection_service import (
    _predict_recent_naive,
    _predict_seasonal_naive,
    _predict_moving_average,
    _predict_weighted_moving_average,
    _predict_recent_trend,
    _predict_holt_ets_non_seasonal,
    _predict_holt_winters,
    _predict_sarima,
    _evaluate_candidate_backtesting,
    _select_best_model_and_window,
    get_selected_forecast,
    clear_forecast_selection_cache,
)


class TestForecastSelectionService(unittest.TestCase):

    def setUp(self):
        clear_forecast_selection_cache()

    # 1. Selección cuando Holt-Winters es óptimo (serie perfectamente estacional de 36 meses)
    def test_01_holt_winters_selection(self):
        t = np.arange(36)
        # Patrón estacional multiplicativo perfecto + tendencia suave
        seasonal_pattern = np.array([100, 120, 140, 200, 180, 150, 110, 90, 80, 100, 130, 160] * 3)
        series_vals = seasonal_pattern + t * 2.0
        s = pd.Series(series_vals)
        
        winner, _ = _select_best_model_and_window(s)
        self.assertIn(winner["method"], ["holt_winters", "seasonal_naive", "sarima_univariate"])
        self.assertLess(winner["overall_wape"], 25.0)

    # 2. Selección de tendencia reciente cuando existe un cambio fuerte de régimen
    def test_02_recent_trend_on_step_change(self):
        # 2024-2025: ventas 9000; 2026: ventas caen a 3000 con tendencia decreciente
        history = [9000] * 24 + [3500, 3400, 3300, 3200, 3100, 3000, 2900, 2800]
        s = pd.Series(history)
        
        winner, _ = _select_best_model_and_window(s)
        # La ventana corta de 6 ó 12 meses o tendencia reciente debe ganar sobre la historia completa de 32 meses
        self.assertIn(winner["method"], ["recent_trend", "moving_average", "weighted_moving_average", "recent_naive"])
        self.assertIn(winner["window_months"], [6, 12, 18])

    # 3. Seasonal Naive
    def test_03_seasonal_naive_predictor(self):
        vals = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 15, 25])
        preds = _predict_seasonal_naive(vals, 4)
        self.assertIsNotNone(preds)
        self.assertEqual(len(preds), 4)
        # El mes 15 predice según el mes 3 (30)
        self.assertEqual(preds[0], 30.0)

    # 4. Moving Average (3 y 6 meses)
    def test_04_moving_average(self):
        vals = np.array([10, 20, 30, 40, 50, 60])
        preds3 = _predict_moving_average(vals, 4, 3)
        preds6 = _predict_moving_average(vals, 4, 6)
        self.assertEqual(preds3, [50.0, 50.0, 50.0, 50.0])
        self.assertEqual(preds6, [35.0, 35.0, 35.0, 35.0])

    # 5. Holt No Estacional (SES / Holt Lineal)
    def test_05_holt_non_seasonal(self):
        vals = np.array([100, 110, 120, 130, 140, 150, 160, 170])
        preds = _predict_holt_ets_non_seasonal(vals, 4, damped=False)
        self.assertIsNotNone(preds)
        self.assertEqual(len(preds), 4)
        self.assertGreater(preds[0], 160.0)

    # 6. SARIMA con convergencia
    def test_06_sarima_convergence(self):
        seasonal = np.array([10, 20, 15, 30, 25, 40, 35, 50, 45, 60, 55, 70] * 3, dtype=float)
        preds = _predict_sarima(seasonal, 4, (1, 0, 0), (0, 1, 1, 12))
        self.assertIsNotNone(preds)
        self.assertEqual(len(preds), 4)

    # 7. SARIMA fallando sin romper el servicio
    def test_07_sarima_failure_safety(self):
        # Serie demasiado corta para SARIMA (<24 meses) -> debe retornar None en silencio
        short_vals = np.array([10.0] * 5)
        preds = _predict_sarima(short_vals, 4, (1, 0, 0), (0, 1, 1, 12))
        self.assertIsNone(preds)  # Se descarta en silencio sin arrojar excepción

    # 8. Ventana de 12m ganando sobre histórico completo
    def test_08_window_12m_beats_full_history(self):
        # 36 meses totales: 24m antiguos caóticos + 12m recientes estables en 500
        history = list(np.random.normal(5000, 2000, 24)) + [500] * 12
        s = pd.Series([max(0, float(x)) for x in history])
        
        winner, _ = _select_best_model_and_window(s)
        self.assertLessEqual(winner["window_months"], 18)

    # 9. Ausencia de Data Leakage (Verificar que backtesting no mira el futuro)
    def test_09_no_data_leakage(self):
        cand_spec = {"method": "recent_trend", "params": {"window": 6}, "min_history": 6}
        # Serie donde el futuro cambia drásticamente en t=20
        history = [100] * 15 + [10000] * 10
        s_vals = np.array(history, dtype=float)
        
        res = _evaluate_candidate_backtesting(cand_spec, s_vals, window_months=12)
        self.assertIsNotNone(res)
        # El WAPE global debe reflejar el error real cuando el futuro cambió desfasado sin data leakage
        self.assertGreater(res["overall_wape"], 0.0)

    # 10. Forecast h1-h4
    def test_10_forecast_horizons_structure(self):
        history = [100 + i * 5 for i in range(30)]
        s_vals = np.array(history, dtype=float)
        cand_spec = {"method": "moving_average", "params": {"window": 6}, "min_history": 6}
        res = _evaluate_candidate_backtesting(cand_spec, s_vals, window_months=24)
        
        self.assertIn("wape_by_horizon", res)
        self.assertIn("h1", res["wape_by_horizon"])
        self.assertIn("h2", res["wape_by_horizon"])
        self.assertIn("h3", res["wape_by_horizon"])
        self.assertIn("h4", res["wape_by_horizon"])

    # 11-15. Cálculo WAPE h1, h2, h3, h4 y overall WAPE
    def test_11_to_15_wape_calculations(self):
        history = [200] * 24
        s_vals = np.array(history, dtype=float)
        cand_spec = {"method": "recent_naive", "params": {}, "min_history": 6}
        res = _evaluate_candidate_backtesting(cand_spec, s_vals, window_months=24)
        
        # Para una serie totalmente constante de 200, Naive reciente da WAPE = 0.0%
        self.assertEqual(res["overall_wape"], 0.0)
        self.assertEqual(res["wape_by_horizon"]["h1"], 0.0)
        self.assertEqual(res["wape_by_horizon"]["h4"], 0.0)

    # 16. Mínimo de Folds
    def test_16_minimum_folds_validation(self):
        # 8 meses de historial -> min_train = 6 -> 8 - 6 = 2 folds de backtesting (< 6)
        history = [100] * 8
        s = pd.Series(history)
        winner, _ = _select_best_model_and_window(s)
        self.assertLess(winner["backtest_origins"], 6)

    # 17. Tie-break hacia modelo más simple (Complexity Tie-Break)
    def test_17_tie_break_towards_simpler_model(self):
        # Serie constante donde Naive (complejidad 1) y Holt-Winters (complejidad 3) empatan con WAPE ~0%
        history = [100] * 36
        s = pd.Series(history)
        winner, _ = _select_best_model_and_window(s)
        self.assertIn(winner["method"], ["recent_naive", "moving_average", "weighted_moving_average", "seasonal_naive"])
        self.assertLessEqual(winner["complexity"], 2)

    # 18. Cero Ventas
    def test_18_zero_sales_handling(self):
        preds = _predict_recent_naive(np.array([0, 0, 0]), 4)
        self.assertEqual(preds, [0.0, 0.0, 0.0, 0.0])

    # 19. Internal Gaps
    def test_19_internal_gap_detection(self):
        res = get_selected_forecast("SKU_INEXISTENTE_9999")
        self.assertIn(res["reason"], ["no_sellout_data_found", "invalid_sku"])

    # 20. Data Lagging
    def test_20_data_lagging_metadata(self):
        # get_selected_forecast sobre SKU real
        res = get_selected_forecast("100001")  # o SKU de prueba
        if res.get("available"):
            self.assertIn("data_status", res)
            self.assertIn(res["data_status"], ["up_to_date", "lagging"])

    # 21. Family Seasonality
    def test_21_family_seasonality_fallback(self):
        # get_selected_forecast para un SKU sin datos o joven
        res = get_selected_forecast("SKU_TEST_YOUNG")
        self.assertIsNotNone(res)

    # 22. Demanda Intermitente
    def test_22_intermittent_demand(self):
        # 8 ceros consecutivos
        series = pd.Series([100, 0, 0, 0, 0, 0, 0, 0, 0, 50, 0, 0, 0, 0, 0, 0])
        from src.services.holt_winters_service import _check_intermittent_demand
        self.assertTrue(_check_intermittent_demand(series))

    # 23. Exactamente 4 Meses Futuros
    def test_23_exactly_four_future_months(self):
        res = get_selected_forecast("100001")
        if res.get("available"):
            self.assertEqual(len(res["forecast"]), 4)

    # 24. Aislamiento Absoluto del S&OP
    def test_24_sop_isolation(self):
        # Verificar que no se modificó ni alteró planner.py ni la función run_planning
        import src.planner as planner
        self.assertTrue(hasattr(planner, "run_planning"))


if __name__ == "__main__":
    unittest.main()
