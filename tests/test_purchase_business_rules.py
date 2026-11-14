import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.planner import (
    COBERTURA_MINIMA_MESES,
    MESES_EXTRA_POR_CRECIMIENTO,
    UMBRAL_CRECIMIENTO_COMPRA_PCT,
    _aplicar_regla_cobertura_compra,
    _cargar_historial_sellout_mensual,
    _estado_excluye_compra,
    _mensualizar_ventas_cuatro_semanas,
)


class PurchaseBusinessRulesTests(unittest.TestCase):
    def test_current_business_rule_constants(self):
        self.assertEqual(COBERTURA_MINIMA_MESES, 5.4)
        self.assertEqual(UMBRAL_CRECIMIENTO_COMPRA_PCT, 5.0)
        self.assertEqual(MESES_EXTRA_POR_CRECIMIENTO, 1.0)

    def test_growth_threshold_adds_exactly_one_month(self):
        configured = pd.Series([5.0, 5.4, 5.4, 7.0])
        growth = pd.Series([4.9, 5.0, 12.5, float("nan")])
        base, detected, extra, target = _aplicar_regla_cobertura_compra(
            configured, growth
        )

        self.assertEqual(base.tolist(), [5.4, 5.4, 5.4, 7.0])
        self.assertEqual(detected.tolist(), [False, True, True, False])
        self.assertEqual(extra.tolist(), [0.0, 1.0, 1.0, 0.0])
        self.assertEqual(target.tolist(), [5.4, 6.4, 6.4, 7.0])

    def test_four_weeks_are_monthlyized_to_thirty_days(self):
        result = _mensualizar_ventas_cuatro_semanas(pd.Series([159, 280]))
        self.assertAlmostEqual(result.iloc[0], 170.357142857, places=6)
        self.assertEqual(result.iloc[1], 300)

    def test_blocked_is_purchased_and_only_discontinued_is_excluded(self):
        self.assertFalse(_estado_excluye_compra("BLOQUEADO"))
        self.assertFalse(_estado_excluye_compra("BLOQUEADOS"))
        self.assertTrue(_estado_excluye_compra("DESCONTINUADO"))
        self.assertTrue(_estado_excluye_compra("INACTIVO"))

    def test_clean_sellout_overrides_stale_validated_history_for_growth(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            pd.DataFrame(
                [
                    {"sku": "7065531", "anio": 2026, "mes": 9, "sellout": 304},
                    {"sku": "7065531", "anio": 2026, "mes": 10, "sellout": 0},
                ]
            ).to_csv(base / "historial_mensual_sku_validado.csv", index=False)
            pd.DataFrame(
                [
                    {"sku": "7065531", "a\u00f1o": 2026, "mes": "septiembre", "unidades_sellout": 304},
                    {"sku": "7065531", "a\u00f1o": 2026, "mes": "octubre", "unidades_sellout": 486},
                ]
            ).to_csv(
                base / "sellout_historico_clean.csv",
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )

            history = _cargar_historial_sellout_mensual(base)
            october = history[
                (history["sku"] == "7065531")
                & (history["anio"] == 2026)
                & (history["mes"] == 10)
            ]

            self.assertEqual(october.iloc[0]["sellout"], 486)


if __name__ == "__main__":
    unittest.main()
