import json
import unittest

import pandas as pd

from src.services.maquila_service import detectar_formato_producto
from src.services.purchase_stock_service import calcular_compra_proyectada


def row(code, description, stock, demand, coverage=4.2, ump=1, transit=None, priority=None):
    transit = transit or [0, 0, 0, 0]
    return {
        "sku": f"SKU-{code}",
        "codigo_femaco": code,
        "nombre_producto": description,
        "stock_act": stock,
        "total_4_sem_verificado": demand,
        "meses_cobertura_objetivo": coverage,
        "ump": ump,
        "prioridad_planificacion": priority,
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
            "prioridad_planificacion": item.get("prioridad_planificacion"),
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
        self.assertEqual(detectar_formato_producto("C-35", "PACK TARUGOS 8 MM"), "CR")
        self.assertEqual(detectar_formato_producto("C-36", "PACK-TARUGOS 8 MM"), "CR")
        self.assertEqual(detectar_formato_producto("C-37", "PACKAGING TARUGOS"), "LINEAL")
        self.assertEqual(
            detectar_formato_producto("C-38", "CINTAS DEMARCA 50MMX33MX 2"),
            "CR",
        )
        self.assertEqual(
            detectar_formato_producto("C-39", "CINTAS DEMARCA 50MMX33M"),
            "LINEAL",
        )
        self.assertEqual(detectar_formato_producto("C-40", "MICRO SOMBRA"), "LINEAL")

    def test_single_sku_uses_four_month_wait_and_confirmed_transit(self):
        source = pd.DataFrame([
            row("IND-1", "Producto individual", 30, 10, ump=12, transit=[0, 20, 0, 0])
        ])
        result = calcular_compra_proyectada(source, {})
        item = result.iloc[0]

        self.assertEqual(item["demanda_espera_4_meses"], 40)
        self.assertEqual(item["stock_estimado_llegada"], 10)
        self.assertEqual(item["stock_objetivo"], 42)
        self.assertEqual(item["sugerencia_bruta"], 32)
        self.assertEqual(item["sugerencia_final"], 36)
        self.assertEqual(item["deficit_espera_4_meses"], 0)

    def test_purchase_prefers_selected_monthly_demand_over_raw_four_weeks(self):
        item = row("MAX-DEMAND", "Producto individual", 100, 28, ump=1)
        item["demanda_mensual_compra"] = 40
        result = calcular_compra_proyectada(pd.DataFrame([item]), {})
        projected = result.iloc[0]

        self.assertEqual(projected["demanda_espera_4_meses"], 160)
        self.assertEqual(projected["stock_objetivo"], 168)
        self.assertEqual(projected["sugerencia_final"], 168)

    def test_four_point_five_months_now_still_requires_purchase(self):
        item = row("SAFE-45", "Producto individual", 450, 100, ump=1)
        item["demanda_mensual_compra"] = 100

        projected = calcular_compra_proyectada(
            pd.DataFrame([item]), {}
        ).iloc[0]

        self.assertEqual(projected["stock_estimado_llegada"], 50)
        self.assertEqual(projected["stock_objetivo"], 420)
        self.assertEqual(projected["sugerencia_bruta"], 370)
        self.assertEqual(projected["sugerencia_final"], 370)

    def test_even_one_unit_gap_at_arrival_generates_purchase(self):
        item = row("SAFE-ONE", "Producto individual", 819, 100, ump=1)
        item["demanda_mensual_compra"] = 100

        projected = calcular_compra_proyectada(
            pd.DataFrame([item]), {}
        ).iloc[0]

        self.assertEqual(projected["stock_estimado_llegada"], 419)
        self.assertEqual(projected["stock_objetivo"], 420)
        self.assertEqual(projected["sugerencia_final"], 1)

    def test_low_stock_growth_case_buys_five_point_two_month_target(self):
        item = row("7065531", "CINTA TELA EXTREM 48MM X 32M", 1800, 507, coverage=5.2, ump=12)
        item["demanda_mensual_compra"] = 507 * 30 / 28

        projected = calcular_compra_proyectada(
            pd.DataFrame([item]), {}
        ).iloc[0]

        self.assertEqual(projected["stock_estimado_llegada"], 0)
        self.assertEqual(projected["stock_objetivo"], 2825)
        self.assertEqual(projected["sugerencia_final"], 2832)

    def test_four_month_average_can_trigger_purchase_despite_low_recent_weeks(self):
        item = row("7781954", "CINTA TELA MULTIUSO 48MMX27M", 10800, 384, coverage=4.2, ump=24)
        item["demanda_mensual_compra"] = (2549 + 1666 + 667 + 464) / 4

        projected = calcular_compra_proyectada(
            pd.DataFrame([item]), {}
        ).iloc[0]

        self.assertEqual(projected["stock_estimado_llegada"], 5454)
        self.assertEqual(projected["stock_objetivo"], 5613)
        self.assertEqual(projected["sugerencia_final"], 168)

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
        self.assertEqual(lineal["sugerencia_final"], 50)
        self.assertEqual(cr["sugerencia_final"], 30)
        self.assertEqual(lineal["familia_compra_total"], 80)

        # Conservacion CR: 100 inicial = 20 venta propia + 80 maquila + 0 final.
        self.assertEqual(
            100,
            20 + cr["maquila_destinada_4_meses"] + cr["stock_estimado_llegada"],
        )

    def test_pack_and_mb_pack_family_use_lineal_and_cr_context(self):
        rows = [
            row("PACK-BASE", "PACK CINTA DEMARCA", 0, 5),
            row("PACK-MB", "MB PACK CINTA DEMARCA", 20, 1),
        ]
        family_data = family(rows, [
            {
                "origen": "PACK-MB",
                "destino": "PACK-BASE",
                "cantidad_origen": 1,
                "cantidad_destino": 1,
            }
        ], family_id=23)
        for family_value in family_data.values():
            family_value["familia_skus"][0]["formato_compra"] = "LINEAL"
            family_value["familia_skus"][1]["formato_compra"] = "CR"

        result = calcular_compra_proyectada(
            pd.DataFrame(rows), family_data, meses_espera=1
        ).set_index("codigo_femaco")

        self.assertEqual(result.loc["PACK-BASE", "formato_compra"], "LINEAL")
        self.assertEqual(result.loc["PACK-MB", "formato_compra"], "CR")
        self.assertEqual(result.loc["PACK-BASE", "prioridad_planificacion"], 1)
        self.assertEqual(result.loc["PACK-MB", "prioridad_planificacion"], 2)

    def test_default_priority_uses_cr_before_furniture(self):
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
        cr = result.loc["AMB-CR"]
        pdq = result.loc["AMB-PDQ"]
        self.assertEqual(lineal["maquila_recibida_4_meses"], 20)
        self.assertEqual(lineal["deficit_espera_4_meses"], 0)
        self.assertEqual(cr["maquila_destinada_4_meses"], 20)
        self.assertEqual(pdq["maquila_destinada_4_meses"], 0)
        self.assertEqual(lineal["ambiguedad_maquila"], "")

    def test_lineal_is_covered_before_cr_own_demand(self):
        rows = [
            row("FIRST-L", "Producto", 0, 5),
            row("FIRST-CR", "Producto CR", 7, 5),
        ]
        conversions = [{
            "origen": "FIRST-CR",
            "destino": "FIRST-L",
            "cantidad_origen": 1,
            "cantidad_destino": 1,
        }]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows),
            family(rows, conversions, family_id=20),
            meses_espera=1,
        ).set_index("codigo_femaco")

        self.assertEqual(result.loc["FIRST-L", "maquila_recibida_4_meses"], 5)
        self.assertEqual(result.loc["FIRST-L", "deficit_espera_4_meses"], 0)
        self.assertEqual(result.loc["FIRST-CR", "deficit_espera_4_meses"], 3)

    def test_missing_recipe_ratio_defaults_to_one_to_one(self):
        rows = [
            row("RATIO-L", "Producto", 0, 4),
            row("RATIO-CR", "Producto CR", 4, 0),
        ]
        conversions = [{
            "origen": "RATIO-CR",
            "destino": "RATIO-L",
            "cantidad_origen": None,
            "cantidad_destino": None,
        }]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows),
            family(rows, conversions, family_id=21),
            meses_espera=1,
        ).set_index("codigo_femaco")

        self.assertEqual(result.loc["RATIO-L", "maquila_recibida_4_meses"], 4)
        self.assertEqual(result.loc["RATIO-CR", "maquila_destinada_4_meses"], 4)

    def test_configured_priority_can_choose_pdq_before_cr(self):
        rows = [
            row("CUSTOM-L", "Producto", 0, 5, priority=1),
            row("CUSTOM-CR", "Producto CR", 10, 0, priority=3),
            row("CUSTOM-PDQ", "Producto PDQ", 10, 0, priority=2),
        ]
        conversions = [
            {"origen": "CUSTOM-CR", "destino": "CUSTOM-L"},
            {"origen": "CUSTOM-PDQ", "destino": "CUSTOM-L"},
        ]
        result = calcular_compra_proyectada(
            pd.DataFrame(rows),
            family(rows, conversions, family_id=22),
            meses_espera=1,
        ).set_index("codigo_femaco")

        self.assertEqual(result.loc["CUSTOM-PDQ", "maquila_destinada_4_meses"], 5)
        self.assertEqual(result.loc["CUSTOM-CR", "maquila_destinada_4_meses"], 0)

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
        self.assertTrue((result["sugerencia_final"] >= 0).all())
        self.assertEqual(result["sugerencia_final"].notna().sum(), 4)
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
