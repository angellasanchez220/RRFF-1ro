import unittest
import pandas as pd
from datetime import date
from api.routes.ordenes_compra import (
    _find_column, _parse_date, _normalize_col_name,
    _detect_quantity_columns, _interpret_estado_y_etapa
)


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

    def test_image_formats_column_detection(self):
        # Layout Imagen 1: SKU consolidado
        cols_img1 = ['BU', 'N° de orden', 'UPC', 'SKU', 'Descripción', 'Unidades', 'Unidades.1', 'Costo', 'Fecha inicio', 'Fecha fin', 'Fecha de creación', 'Tipo de entrega', 'Entrega en', 'Vin']
        pat_oc = [r"^(?:n[úu]mero|nro|n°)[_\s]*(?:oc|compra|orden|pedido)?.*$", r"n[úu]mero.*", r"n°.*orden", r"orden[_\s]*compra", r"^oc$", r"^pedido$"]
        pat_sku = [r"^(?:sku|material|item)$", r"sku.*", r"c[oó]digo"]
        pat_vin = [r"^(?:vin|vendor[_\s]*item[_\s]*number)$", r"c[oó]d(?:igo)?[_\s]*femaco", r"c[oó]d(?:igo)?[_\s]*interno", r"^c[oó]digo$"]
        pat_desc = [r"^(?:nombre|nombre[_\s]*producto|descripci[oó]n|producto|modelo)$", r"descripci[oó]n.*"]

        self.assertEqual(_find_column(cols_img1, pat_oc), "N° de orden")
        self.assertEqual(_find_column(cols_img1, pat_sku), "SKU")
        self.assertEqual(_find_column(cols_img1, pat_vin), "Vin")
        self.assertEqual(_find_column(cols_img1, pat_desc), "Descripción")

        col_p, col_d = _detect_quantity_columns(cols_img1)
        self.assertEqual(col_p, "Unidades")
        self.assertEqual(col_d, "Unidades.1")

        # Layout Imagen 2 y 3: Desglose por tienda/local con Estado OC
        cols_img2 = ['Ítem', 'Fecha de creación', 'Número OC', 'Estado OC', 'Tipo de orden', 'Fecha de emisión', 'Fecha inicio', 'Fecha fin', 'Tax id proveedor', 'Razón social', 'ID lugar de entrega', 'Descripción', 'Dirección', 'UPC', 'SKU', 'Modelo', 'VIN', 'Unidad de medida', 'Nro capas', 'Empaq caja', 'Id de local', 'Local', 'Unidades', 'Unidades.1', 'Cantidad confirmada', 'Pasillo', 'Lineal', 'Metro']
        pat_estado = [r"^(?:estado[_\s]*oc|estado|status|situaci[oó]n)$", r"estado.*"]

        self.assertEqual(_find_column(cols_img2, pat_oc), "Número OC")
        self.assertEqual(_find_column(cols_img2, pat_sku), "SKU")
        self.assertEqual(_find_column(cols_img2, pat_vin), "VIN")
        self.assertEqual(_find_column(cols_img2, pat_estado), "Estado OC")

        col_p2, col_d2 = _detect_quantity_columns(cols_img2)
        self.assertEqual(col_p2, "Unidades")
        self.assertEqual(col_d2, "Unidades.1")

    def test_interpret_estado_y_etapa(self):
        # Cursado -> PEDIDO
        etapa, estado = _interpret_estado_y_etapa("Cursado", sum_ped=44, sum_desp=0, user_etapa="AUTO")
        self.assertEqual(etapa, "PEDIDO")
        self.assertEqual(estado, "CURSADO")

        # Recepción -> ENTREGA
        etapa_r, estado_r = _interpret_estado_y_etapa("Recepción", sum_ped=44, sum_desp=44, user_etapa="AUTO")
        self.assertEqual(etapa_r, "ENTREGA")
        self.assertEqual(estado_r, "RECEPCIONADO")

        # Forzado por usuario
        etapa_f, estado_f = _interpret_estado_y_etapa("Cursado", sum_ped=44, sum_desp=0, user_etapa="ENTREGA")
        self.assertEqual(etapa_f, "ENTREGA")

    def test_store_consolidation_math(self):
        # Simular filas de Imagen 2: dos locales para el mismo SKU/VIN
        rows = [
            {"sku": "5522900", "vin": "T1001", "local": "HC 23 San", "ped": 22, "desp": 0},
            {"sku": "5522900", "vin": "T1001", "local": "HC 66 Nub", "ped": 22, "desp": 0},
            {"sku": "5523621", "vin": "F2450", "local": "HC 20 Vin", "ped": 12, "desp": 0},
            {"sku": "5523621", "vin": "F2450", "local": "HC 83 Ran", "ped": 12, "desp": 0},
            {"sku": "5523621", "vin": "F2450", "local": "HC 742 La", "ped": 12, "desp": 0},
        ]
        consolidated = {}
        for r in rows:
            key = (r["sku"], r["vin"])
            if key not in consolidated:
                consolidated[key] = {"cant_p": 0, "cant_d": 0}
            consolidated[key]["cant_p"] += r["ped"]
            consolidated[key]["cant_d"] += r["desp"]

        # Debe coincidir exactamente con los totales de Imagen 1
        self.assertEqual(consolidated[("5522900", "T1001")]["cant_p"], 44)
        self.assertEqual(consolidated[("5523621", "F2450")]["cant_p"], 36)

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
        items = [
            {"sku": "SKU-1", "codigo_femaco": "COD-1", "familia_id": 10, "cantidad_pedida": 50, "cantidad_despachada": 50},
            {"sku": "SKU-2", "codigo_femaco": "COD-2", "familia_id": 10, "cantidad_pedida": 100, "cantidad_despachada": 0},
        ]
        
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
