import unittest
from unittest.mock import patch

import pandas as pd

from src.services.maquila_service import build_maquila_families


class BuildMaquilaFamiliesTests(unittest.TestCase):
    @patch("src.services.maquila_service.pd.read_sql")
    def test_connected_families_include_all_members_and_total_stock(self, read_sql):
        read_sql.return_value = pd.DataFrame([
            {
                "familia_id": 1,
                "sku_maquilable": "FAM-ONE",
                "nombre_familia": "Tiras removibles",
                "sku_componente": "SKU-A",
                "no_transformable": False,
            },
            {
                "familia_id": 1,
                "sku_maquilable": "FAM-ONE",
                "nombre_familia": "Tiras removibles",
                "sku_componente": "SKU-B",
                "no_transformable": False,
            },
            {
                "familia_id": 2,
                "sku_maquilable": "FAM-TWO",
                "nombre_familia": "Tiras conectadas",
                "sku_componente": "SKU-B",
                "no_transformable": False,
            },
            {
                "familia_id": 2,
                "sku_maquilable": "FAM-TWO",
                "nombre_familia": "Tiras conectadas",
                "sku_componente": "SKU-C",
                "no_transformable": True,
            },
        ])
        lookup = {
            "SKU-A": {"nombre_producto": "Producto A", "stock_act": 10, "ritmo_mensual": 2},
            "SKU-B": {"nombre_producto": "Producto B", "stock_act": 20, "ritmo_mensual": 4},
            "SKU-C": {"nombre_producto": "Producto C", "stock_act": 5, "ritmo_mensual": 1},
        }

        result = build_maquila_families(object(), lookup)

        self.assertEqual(set(result), {"SKU-A", "SKU-B", "SKU-C"})
        self.assertEqual([m["sku"] for m in result["SKU-A"]["familia_skus"]], ["SKU-A", "SKU-B", "SKU-C"])
        self.assertEqual(result["SKU-A"]["stock_bruto_familia"], 35)
        self.assertEqual(result["SKU-A"]["cantidad_miembros"], 3)
        self.assertEqual(result["SKU-A"]["familia_ids"], [1, 2])
        self.assertEqual(result["SKU-A"]["nombres_familia"], ["Tiras conectadas", "Tiras removibles"])
        self.assertTrue(next(m for m in result["SKU-A"]["familia_skus"] if m["sku"] == "SKU-C")["no_transformable"])


if __name__ == "__main__":
    unittest.main()
