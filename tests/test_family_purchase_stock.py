import unittest

import pandas as pd

from src.services.purchase_stock_service import aplicar_stock_familia_para_sugerencia


class FamilyPurchaseStockTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {"sku": "SKU-1", "stock_act": 10},
            {"sku": "SKU-2", "stock_act": 140},
            {"sku": "SKU-SIN-FAMILIA", "stock_act": 25},
        ])
        miembros = [
            {"sku": "SKU-1", "stock_act": 10},
            {"sku": "SKU-2", "stock_act": 140},
        ]
        self.familias = {
            "SKU-1": {
                "familia_skus": miembros,
                "stock_bruto_familia": 150,
                "nombre_familia": "Familia de prueba",
            },
            "SKU-2": {
                "familia_skus": miembros,
                "stock_bruto_familia": 150,
                "nombre_familia": "Familia de prueba",
            },
        }

    def test_family_total_replaces_individual_stock_for_purchase(self):
        result = aplicar_stock_familia_para_sugerencia(self.df, self.familias)
        sku_1 = result.loc[result["sku"] == "SKU-1"].iloc[0]

        self.assertEqual(sku_1["sug_stock_individual"], 10)
        self.assertEqual(sku_1["sug_stock_familia"], 150)
        self.assertEqual(sku_1["sug_stock_actual"], 150)
        self.assertTrue(sku_1["sug_usa_stock_familia"])

        # Caso solicitado: target 139, stock SKU 10, pero familia 150.
        sugerencia = max(139 - sku_1["sug_stock_actual"], 0)
        self.assertEqual(sugerencia, 0)

    def test_family_deficit_is_calculated_against_total_family_stock(self):
        result = aplicar_stock_familia_para_sugerencia(self.df, self.familias)
        sku_1 = result.loc[result["sku"] == "SKU-1"].iloc[0]

        sugerencia = max(200 - sku_1["sug_stock_actual"], 0)
        self.assertEqual(sugerencia, 50)

    def test_sku_without_family_keeps_its_individual_stock(self):
        result = aplicar_stock_familia_para_sugerencia(self.df, self.familias)
        sku = result.loc[result["sku"] == "SKU-SIN-FAMILIA"].iloc[0]

        self.assertEqual(sku["sug_stock_actual"], 25)
        self.assertFalse(sku["sug_usa_stock_familia"])


if __name__ == "__main__":
    unittest.main()
