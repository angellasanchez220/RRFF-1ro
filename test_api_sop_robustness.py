import pandas as pd
import numpy as np

def _calc_alerta(row):
    dur = row["duracion_fisica_solo"]
    al = "VERDE"
    if dur > 10: al = "AZUL"
    elif dur < 4: al = "AMARILLO"
    if dur < 2.5: al = "NARANJA"
    if dur < 1.0: al = "ROJO"
    
    cantidad_transito = row.get("cantidad_transito", 0) or 0
    eta_proxima = row.get("eta_proxima", pd.NaT)
    
    if cantidad_transito > 0 and pd.notna(eta_proxima):
        al = "MORADO"
    return al

def test_sku_con_transito_y_eta():
    row = {
        "duracion_fisica_solo": 0.5,
        "cantidad_transito": 100,
        "eta_proxima": pd.to_datetime("2026-10-01")
    }
    assert _calc_alerta(row) == "MORADO"
    print("test_sku_con_transito_y_eta PASSED")

def test_sku_sin_transito():
    row = {
        "duracion_fisica_solo": 0.5,
        "cantidad_transito": 0,
        "eta_proxima": pd.to_datetime("2026-10-01")
    }
    assert _calc_alerta(row) == "ROJO"
    print("test_sku_sin_transito PASSED")

def test_dataframe_sin_columna_eta_proxima():
    row = {
        "duracion_fisica_solo": 0.5,
        "cantidad_transito": 100
    }
    assert _calc_alerta(row) == "ROJO"
    print("test_dataframe_sin_columna_eta_proxima PASSED")

def test_dataframe_vacio_de_transitos():
    row = {
        "duracion_fisica_solo": 0.5
    }
    assert _calc_alerta(row) == "ROJO"
    print("test_dataframe_vacio_de_transitos PASSED")

if __name__ == "__main__":
    test_sku_con_transito_y_eta()
    test_sku_sin_transito()
    test_dataframe_sin_columna_eta_proxima()
    test_dataframe_vacio_de_transitos()
    print("All tests passed successfully!")
