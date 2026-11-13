import json
import unittest

import pandas as pd

from src.services.maquila_service import detectar_formato_producto
from src.services.purchase_stock_service import calcular_compra_proyectada


def row(code, description, stock, demand, coverage=5.4, ump=1, transit=None):
    transit = transit or [0, 0, 0, 0]
    return {
        "sku": f"SKU-{code}",
        "codigo_femaco": code,
        "nombre_producto": description,
        "stock_act": stock,
        "total_4_sem_verificado": demand,
        "meses_cobertura_objetivo": coverage,
        "ump": ump,
        "transito_mes_1": transit[0],
        "transito_mes_2": transit[1],
        "transito_mes_3": transit[2],
        "transito_mes_4": transit[3],
    }


def family(rows, conversions=None, family_id=1):
    members = [
        {
            "codigo_femaco": item["codigo_femaco"],
            "sku": item["sku"],
            "stock_act": item["stock_act"],
        }
        for item in rows
    ]
    data = {
        "familia_skus": members,
        "familia_ids": [family_id],
        "clave_familia": f"FAM:{family_id}",
        "nombre_familia": f"Familia {family_id}",
        "conversiones_autorizadas": conversions or [],
    }
    return {item["codigo_femaco"]: data for item in rows}


class ProjectedPurchaseTests(unittest.TestCase):
    def test_format_detection_avoids_accidental_words(self):
        self.assertEqual(detectar_formato_producto("C9405CR", "Producto"), "CR")
        self.assertEqual(detectar_formato_producto("C-20", "Pack-PDQ"), "PDQ")
        self.assertEqual(detectar_formato_producto("C-30", "Formato MB 20"), "MB")
        self.assertEqual(detectar_formato_producto("C-40", "MICRO SOMBRA"), "LINEAL")

    def test_single_sku_uses_four_month_wait_and_confirmed_transit(self):
        source = pd.DataFrame([
            row("IND-1", "Producto individual", 30, 10, ump=12, transit=[0, 20, 0, 0])
        ])
        result = calcular_compra_proyectada(source, {})
        item = result.iloc[0]

        self.assertEqual(item["demanda_espera_4_meses"], 40)
        self.assertEqual(item["stock_estimado_llegada"], 10)
        self.assertEqual(item["stock_objetivo"], 54)
        self.assertEqual(item["sugerencia_bruta"], 44)
        self.assertEqual(item["sugerencia_final"], 48)
        self.assertEqual(item["deficit_espera_4_meses"], 0)

    def test_transit_without_confirmed_eta_is_not_used(self):
        item = row("NO-ETA", "Producto individual", 0, 5)
        for month in range(1, 5):
            item.pop(f"transito_mes_{month}")
        item["cantidad_transito"] = 100
        item["cantidad_transito_confirmado_4m"] = 0

        result = calcular_compra_proyectada(pd.DataFrame([item]), {})
        projected = result.iloc[0]
        self.assertEqual(projected["sug_transito_actual"], 0)
        self.assertEqual(projected["stock_estimado_llegada"], 0)
        self.assertEqual(projected["deficit_espera_4_meses"], 20)

    def test_two_formats_consume_own_sales_then_transform_by_recipe(self):
        rows = [
            row("FAM-L", "Producto base", 0, 10, ump=10),
            row("FAM-CR", "Producto CR", 100, 5, ump=10),
        ]
        conversions = [{
            "receta_id": 7,
            "origen": "FAM-CR",
            "destino": "FAM-L",
            "cantidad_origen": 2,
            "cantidad_destino": 1,
            "prioridad": None,
        }]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows),
            family(rows, conversions),
        ).set_index("codigo_femaco")

        lineal = result.loc["FAM-L"]
        cr = result.loc["FAM-CR"]
        self.assertEqual(lineal["maquila_recibida_4_meses"], 40)
        self.assertEqual(lineal["deficit_espera_4_meses"], 0)
        self.assertEqual(cr["maquila_destinada_4_meses"], 80)
        self.assertEqual(cr["stock_estimado_llegada"], 0)
        self.assertEqual(lineal["sugerencia_final"], 60)
        self.assertEqual(cr["sugerencia_final"], 30)
        self.assertEqual(lineal["familia_compra_total"], 90)

        # Conservacion CR: 100 inicial = 20 venta propia + 80 maquila + 0 final.
        self.assertEqual(
            100,
            20 + cr["maquila_destinada_4_meses"] + cr["stock_estimado_llegada"],
        )

    def test_three_formats_without_priority_reports_ambiguity(self):
        rows = [
            row("AMB-L", "Producto", 0, 5),
            row("AMB-CR", "Producto CR", 30, 1),
            row("AMB-PDQ", "Producto PDQ", 30, 1),
        ]
        conversions = [
            {"origen": "AMB-CR", "destino": "AMB-L", "cantidad_origen": 1, "cantidad_destino": 1, "prioridad": None},
            {"origen": "AMB-PDQ", "destino": "AMB-L", "cantidad_origen": 1, "cantidad_destino": 1, "prioridad": None},
        ]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows), family(rows, conversions, family_id=2)
        ).set_index("codigo_femaco")

        lineal = result.loc["AMB-L"]
        self.assertEqual(lineal["maquila_recibida_4_meses"], 0)
        self.assertEqual(lineal["deficit_espera_4_meses"], 20)
        self.assertIn("sin prioridad", lineal["ambiguedad_maquila"])

    def test_four_formats_generate_four_purchases_and_family_summary(self):
        rows = [
            row("FOUR-L", "Producto", 0, 4),
            row("FOUR-CR", "Producto CR", 20, 2),
            row("FOUR-PDQ", "Producto PDQ", 12, 1),
            row("FOUR-MB", "Producto MB", 8, 1),
        ]
        conversions = [
            {"origen": "FOUR-CR", "destino": "FOUR-L", "cantidad_origen": 1, "cantidad_destino": 1, "prioridad": 1},
            {"origen": "FOUR-PDQ", "destino": "FOUR-L", "cantidad_origen": 1, "cantidad_destino": 1, "prioridad": 2},
            {"origen": "FOUR-MB", "destino": "FOUR-L", "cantidad_origen": 1, "cantidad_destino": 1, "prioridad": 3},
        ]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows), family(rows, conversions, family_id=3)
        )

        self.assertEqual(set(result["formato_compra"]), {"LINEAL", "CR", "PDQ", "MB"})
        self.assertEqual(len(result), 4)
        self.assertTrue((result["sugerencia_final"] > 0).all())
        self.assertTrue((result["stock_estimado_llegada"] >= 0).all())

        summary = json.loads(result.iloc[0]["familia_resumen_compras"])
        self.assertEqual(len(summary["formatos"]), 4)
        self.assertEqual(
            summary["total"],
            result["sugerencia_final"].sum(),
        )

    def test_growth_coverage_is_applied_per_sku(self):
        source = pd.DataFrame([
            row("GROWTH", "Producto", 0, 10, coverage=6.4, ump=1)
        ])
        result = calcular_compra_proyectada(source, {})
        self.assertEqual(result.iloc[0]["stock_objetivo"], 64)
        self.assertEqual(result.iloc[0]["sugerencia_final"], 64)


if __name__ == "__main__":
    unittest.main()

