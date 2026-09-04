import unittest
from unittest.mock import patch

import pandas as pd

from src.services.maquila_service import (
    build_maquila_families,
    build_product_lookup_by_internal_code,
)


class BuildMaquilaFamiliesTests(unittest.TestCase):
    def test_lookup_ignores_empty_and_repeated_internal_codes(self):
        productos = pd.DataFrame([
            {"codigo_femaco": None, "sku": "SIN-COD-1", "stock_act": 9},
            {"codigo_femaco": "", "sku": "SIN-COD-2", "stock_act": 8},
            {
                "codigo_femaco": " cod-a ",
                "sku": "SKU-A",
                "nombre_producto": "Producto A",
                "stock_act": 10,
                "total_4_sem_verificado": 2,
            },
            {
                "codigo_femaco": "COD-A",
                "sku": "SKU-DUPLICADO",
                "nombre_producto": "No debe reemplazar al primero",
                "stock_act": 999,
                "total_4_sem_verificado": 999,
            },
        ])

        lookup = build_product_lookup_by_internal_code(
            productos,
            ritmo_col="total_4_sem_verificado",
        )

        self.assertEqual(set(lookup), {"COD-A"})
        self.assertEqual(lookup["COD-A"]["sku"], "SKU-A")
        self.assertEqual(lookup["COD-A"]["stock_act"], 10)
        self.assertEqual(lookup["COD-A"]["ritmo_mensual"], 2)

    @patch("src.services.maquila_service.pd.read_sql")
    def test_connected_families_include_all_members_and_total_stock(self, read_sql):
        read_sql.return_value = pd.DataFrame([
            {
                "familia_id": 1,
                "sku_maquilable": "FAM-ONE",
                "nombre_familia": "Tiras removibles",
                "sku_componente": "COD-A",
                "no_transformable": False,
            },
            {
                "familia_id": 1,
                "sku_maquilable": "FAM-ONE",
                "nombre_familia": "Tiras removibles",
                "sku_componente": "COD-B",
                "no_transformable": False,
            },
            {
                "familia_id": 2,
                "sku_maquilable": "FAM-TWO",
                "nombre_familia": "Tiras conectadas",
                "sku_componente": "COD-B",
                "no_transformable": False,
            },
            {
                "familia_id": 2,
                "sku_maquilable": "FAM-TWO",
                "nombre_familia": "Tiras conectadas",
                "sku_componente": "COD-C",
                "no_transformable": True,
            },
        ])
        lookup = {
            "COD-A": {"sku": "SKU-A", "nombre_producto": "Producto A", "stock_act": 10, "ritmo_mensual": 2},
            "COD-B": {"sku": "SKU-B", "nombre_producto": "Producto B", "stock_act": 20, "ritmo_mensual": 4},
            "COD-C": {"sku": "SKU-C", "nombre_producto": "Producto C", "stock_act": 5, "ritmo_mensual": 1},
        }

        result = build_maquila_families(object(), lookup)

        self.assertEqual(set(result), {"COD-A", "COD-B", "COD-C"})
        familia = result["COD-A"]
        self.assertEqual([m["codigo_femaco"] for m in familia["familia_skus"]], ["COD-A", "COD-B", "COD-C"])
        self.assertEqual([m["sku"] for m in familia["familia_skus"]], ["SKU-A", "SKU-B", "SKU-C"])
        self.assertEqual(familia["stock_bruto_familia"], 35)
        self.assertEqual(familia["cantidad_miembros"], 3)
        self.assertEqual(familia["familia_ids"], [1, 2])
        self.assertEqual(familia["nombres_familia"], ["Tiras conectadas", "Tiras removibles"])
        self.assertTrue(next(m for m in familia["familia_skus"] if m["codigo_femaco"] == "COD-C")["no_transformable"])


if __name__ == "__main__":
    unittest.main()
