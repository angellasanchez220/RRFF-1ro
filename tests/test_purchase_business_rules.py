import unittest

import pandas as pd

from src.planner import (
    COBERTURA_MINIMA_MESES,
    MESES_EXTRA_POR_CRECIMIENTO,
    UMBRAL_CRECIMIENTO_COMPRA_PCT,
    _aplicar_regla_cobertura_compra,
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


if __name__ == "__main__":
    unittest.main()
