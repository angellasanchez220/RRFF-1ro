import unittest
import pandas as pd
from unittest.mock import MagicMock

# Mock simple para probar _resolver_cobertura
class TestCoberturaResolucion(unittest.TestCase):
    def test_resolver_cobertura(self):
        dict_sku = {"SKU123": 3.0}
        dict_cat = {"MADERAS": 6.0}
        global_val = 4.0
        global_val_exists = True

        def _resolver_cobertura(row):
            sku = str(row.get("sku", ""))
            cat = str(row.get("categoria", ""))
            if sku in dict_sku:
                return float(dict_sku[sku]), "SKU"
            if pd.notna(row.get("categoria")) and cat in dict_cat:
                return float(dict_cat[cat]), "CATEGORIA"
            if global_val_exists:
                return global_val, "GLOBAL"
            return 5.0, "FALLBACK"

        # 1. Test SKU Override
        res1 = _resolver_cobertura({"sku": "SKU123", "categoria": "MADERAS"})
        self.assertEqual(res1, (3.0, "SKU"))

        # 2. Test Categoria Override
        res2 = _resolver_cobertura({"sku": "SKU999", "categoria": "MADERAS"})
        self.assertEqual(res2, (6.0, "CATEGORIA"))

        # 3. Test Global Fallback
        res3 = _resolver_cobertura({"sku": "SKU999", "categoria": "FERRETERIA"})
        self.assertEqual(res3, (4.0, "GLOBAL"))

        # 4. Test Fallback (No Global Config)
        global_val_exists = False
        res4 = _resolver_cobertura({"sku": "SKU999", "categoria": "FERRETERIA"})
        self.assertEqual(res4, (5.0, "FALLBACK"))

    def test_sugerencia_bruta_no_negativa(self):
        # Sugerencia bruta = sug_target_uds - inv_disponible.clip(lower=0)
        sug_target_uds = pd.Series([100, 50, 0])
        inv_disponible = pd.Series([80, 100, 10])
        sug_bruta = sug_target_uds - inv_disponible
        sug_bruta_clipped = sug_bruta.clip(lower=0)
        self.assertEqual(sug_bruta_clipped.tolist(), [20, 0, 0])

    def test_redondeo_ump(self):
        import math
        def _ceil_to_multiple(value, multiple):
            if not multiple or multiple <= 0 or math.isnan(multiple):
                return value
            return math.ceil(value / multiple) * multiple

        self.assertEqual(_ceil_to_multiple(23, 10), 30)
        self.assertEqual(_ceil_to_multiple(0, 10), 0)
        self.assertEqual(_ceil_to_multiple(5, 0), 5)
        self.assertEqual(_ceil_to_multiple(1, 2.5), 2.5)

if __name__ == "__main__":
    unittest.main()
