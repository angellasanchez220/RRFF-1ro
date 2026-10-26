import unittest
import pandas as pd
from datetime import date
from api.routes.ordenes_compra import _find_column, _parse_date, _normalize_col_name


class OrdenesCompraTests(unittest.TestCase):
    def test_find_column_flexible_matching(self):
        cols = ["N° OC", "Cod. Interno", "Producto / Modelo", "Cantidad Pedida", "Unidades Recibidas"]
        col_oc = _find_column(cols, [r"^(?:n[úu]mero[_\s]*oc|nro[_\s]*oc|orden[_\s]*compra|oc|pedido)$", r"n[úu]mero.*orden", r"nro.*pedido", r"n°.*oc"])
        col_sku = _find_column(cols, [r"^(?:sku|c[oó]digo|c[oó]digo[_\s]*femaco|cod[_\s]*femaco|material|item)$", r"cod.*interno"])
        col_ped = _find_column(cols, [r"cant(?:idad)?[_\s]*(?:pedida|solicitada|comprada)", r"unidades[_\s]*(?:pedidas|compradas)"])
        col_desp = _find_column(cols, [r"cant(?:idad)?[_\s]*(?:despachada|entregada|recibida)", r"unidades[_\s]*(?:despachadas|entregadas|recibidas)"])

        self.assertEqual(col_oc, "N° OC")
        self.assertEqual(col_sku, "Cod. Interno")
        self.assertEqual(col_ped, "Cantidad Pedida")
        self.assertEqual(col_desp, "Unidades Recibidas")

    def test_parse_date(self):
        d1 = _parse_date("2026-10-20")
        d2 = _parse_date("20/10/2026")
        self.assertEqual(d1, date(2026, 10, 20))
        self.assertEqual(d2, date(2026, 10, 20))
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date(None))

    def test_normalize_col_name(self):
        self.assertEqual(_normalize_col_name(" Cantidad  Despachada (Uds) "), "cantidad_despachada_uds")

    def test_family_imbalance_detection_logic(self):
        # Familia con 2 productos: uno despachado y otro no despachado
        items = [
            {"sku": "SKU-1", "codigo_femaco": "COD-1", "familia_id": 10, "cantidad_pedida": 50, "cantidad_despachada": 50},
            {"sku": "SKU-2", "codigo_femaco": "COD-2", "familia_id": 10, "cantidad_pedida": 100, "cantidad_despachada": 0},
        ]
        
        # Agrupar por familia
        fam_groups = {}
        for it in items:
            fam_groups.setdefault(it["familia_id"], []).append(it)

        desbalance_detected = False
        for fid, f_items in fam_groups.items():
            despachados = [it for it in f_items if it["cantidad_despachada"] > 0]
            no_despachados = [it for it in f_items if it["cantidad_despachada"] == 0]
            if despachados and no_despachados:
                desbalance_detected = True

        self.assertTrue(desbalance_detected)

    def test_quiebre_recovery_days_logic(self):
        fecha_quiebre = date(2026, 10, 1)
        fecha_recuperacion = date(2026, 10, 29)
        dias_recuperacion = (fecha_recuperacion - fecha_quiebre).days
        self.assertEqual(dias_recuperacion, 28)


if __name__ == "__main__":
    unittest.main()
