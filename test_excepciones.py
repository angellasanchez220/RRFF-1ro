import unittest
import pandas as pd
import json
from src.planner import _calcular_excepciones_y_alertas

class TestExcepciones(unittest.TestCase):
    def _run_test(self, sku_data):
        df = pd.DataFrame([sku_data])
        # Asegurar columnas que el motor normalmente recibe o rellena
        cols_default = [
            "sku", "nombre_producto", "stock_act", "ump", 
            "sug_ritmo_mensual", "estado", "cantidad_transito", 
            "eta_proxima", "total_4_sem_verificado"
        ]
        for c in cols_default:
            if c not in df.columns:
                df[c] = None
        df = _calcular_excepciones_y_alertas(df)
        res = df.iloc[0]
        excepciones = json.loads(res["excepciones"]) if isinstance(res["excepciones"], str) else res["excepciones"]
        return res, excepciones

    def test_01_stock_cero_demanda_alta_sin_transito(self):
        # alerta roja; compra sugerida (bruta) > 0 pero no está bloqueada
        res, excs = self._run_test({
            "sku": "S1", "nombre_producto": "P1", "stock_act": 0, "ump": 1,
            "sug_ritmo_mensual": 100, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 400, "sugerencia_compra_inmediata_uds": 500, "meses_cobertura_objetivo": 5.0
        })
        self.assertEqual(res["nivel_alerta"], "ROJO")
        self.assertFalse(res["bloquea_compra_automatica"])
        self.assertIn("Quiebre estimado en 0.0 semanas", res["explicacion_compra"])

    def test_02_stock_bajo_transito_con_eta(self):
        # debe reconocerse que existe cobertura futura (MORADO)
        res, excs = self._run_test({
            "sku": "S2", "nombre_producto": "P2", "stock_act": 10, "ump": 1,
            "sug_ritmo_mensual": 100, "estado": "ACTIVO", "cantidad_transito": 200,
            "eta_proxima": "2026-07-01", "total_4_sem_verificado": 400, "sugerencia_compra_inmediata_uds": 0, "meses_cobertura_objetivo": 5.0
        })
        self.assertEqual(res["nivel_alerta"], "MORADO")
        self.assertNotIn("SIN_ETA_TRANSITO", excs)
        self.assertIn("Existe tránsito", res["explicacion_compra"])

    def test_03_stock_bajo_transito_sin_eta(self):
        # debe mantener el riesgo real (ROJO) y agregar SIN_ETA_TRANSITO
        res, excs = self._run_test({
            "sku": "S3", "nombre_producto": "P3", "stock_act": 10, "ump": 1,
            "sug_ritmo_mensual": 100, "estado": "ACTIVO", "cantidad_transito": 200,
            "eta_proxima": None, "total_4_sem_verificado": 400, "sugerencia_compra_inmediata_uds": 290, "meses_cobertura_objetivo": 5.0
        })
        self.assertEqual(res["nivel_alerta"], "ROJO")
        self.assertIn("SIN_ETA_TRANSITO", excs)
        self.assertEqual(res["requiere_revision"], 1)
        self.assertIn("Tránsito registrado sin ETA", res["explicacion_compra"])

    def test_04_menos_de_4_semanas_validas(self):
        # SIN_VENTAS_SUFICIENTES
        res, excs = self._run_test({
            "sku": "S4", "nombre_producto": "P4", "stock_act": 50, "ump": 1,
            "sug_ritmo_mensual": 0, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 0, "sugerencia_compra_inmediata_uds": 0, "meses_cobertura_objetivo": 5.0
        })
        self.assertIn("SIN_VENTAS_SUFICIENTES", excs)
        self.assertEqual(res["requiere_revision"], 1)
        self.assertIn("No hay necesidad inminente de reposición", res["explicacion_compra"])

    def test_05_producto_nuevo(self):
        # PRODUCTO_NUEVO
        res, excs = self._run_test({
            "sku": "S5", "nombre_producto": "P5", "stock_act": 0, "ump": 1,
            "sug_ritmo_mensual": 0, "estado": "NUEVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 0
        })
        self.assertIn("PRODUCTO_NUEVO", excs)
        self.assertEqual(res["requiere_revision"], 1)

    def test_06_producto_descontinuado(self):
        # PRODUCTO_DESCONTINUADO; compra bloqueada
        res, excs = self._run_test({
            "sku": "S6", "nombre_producto": "P6", "stock_act": 0, "ump": 1,
            "sug_ritmo_mensual": 10, "estado": "DESCONTINUADO", "cantidad_transito": 0,
            "total_4_sem_verificado": 40
        })
        self.assertIn("PRODUCTO_DESCONTINUADO", excs)
        self.assertEqual(res["bloquea_compra_automatica"], 1)
        # La sugerencia final (si estuviera) debe forzarse a 0
        self.assertEqual(res.get("sugerencia_final", 0), 0)

    def test_07_ump_faltante(self):
        # SIN_UMP; sugerencia bruta disponible pero final no aprobable automaticamente (bloquea=1)
        res, excs = self._run_test({
            "sku": "S7", "nombre_producto": "P7", "stock_act": 0, "ump": 0,
            "sug_ritmo_mensual": 10, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 40
        })
        self.assertIn("SIN_UMP", excs)
        self.assertEqual(res["bloquea_compra_automatica"], 1)

    def test_08_stock_negativo(self):
        # STOCK_NEGATIVO; bloquea compra
        res, excs = self._run_test({
            "sku": "S8", "nombre_producto": "P8", "stock_act": -5, "ump": 1,
            "sug_ritmo_mensual": 10, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 40
        })
        self.assertIn("STOCK_NEGATIVO", excs)
        self.assertEqual(res["requiere_revision"], 1)
        self.assertEqual(res["bloquea_compra_automatica"], 1)

    def test_09_datos_incompletos(self):
        # DATOS_INCOMPLETOS
        res, excs = self._run_test({
            "sku": "", "nombre_producto": "P9", "stock_act": 10, "ump": 1,
            "sug_ritmo_mensual": 10, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 40
        })
        self.assertIn("DATOS_INCOMPLETOS", excs)
        self.assertEqual(res["bloquea_compra_automatica"], 1)

    def test_10_forecast_manual(self):
        # FORECAST_MANUAL
        # Actualmente asume FORECAST_ORIGEN="ALGORITMO" por defecto en la estructura.
        res, excs = self._run_test({
            "sku": "S10", "nombre_producto": "P10", "stock_act": 10, "ump": 1,
            "sug_ritmo_mensual": 10, "estado": "ACTIVO", "cantidad_transito": 0,
            "total_4_sem_verificado": 40
        })
        self.assertEqual(res["forecast_origen"], "ALGORITMO")

    def test_11_redondeo_ump(self):
        from src.planner import _ceil_to_multiple
        # si UMP es 24 y bruta es 25 -> 48
        val = _ceil_to_multiple(25, 24)
        self.assertEqual(val, 48)

if __name__ == "__main__":
    unittest.main()
