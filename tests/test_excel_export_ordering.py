from datetime import date
from unittest.mock import patch

from api.routes.sop import _get_mes_map
from src.services.excel_export_service import (
    _product_family_sort_key,
    _assign_family_colors,
    _deduplicate_export_data,
    _safe_sheet_name,
    _poblar_caja_calculo_cr,
    _calcular_coberturas_compra_export,
    _calcular_fecha_compra,
    _enriquecer_metricas_familia,
    _poblar_caja_resumen_lineal,
    copiar_bloque,
    poblar_bloque,
)
from src.transformer import _read_inventario_excel


def _item(sku, nombre, familia="Familia Sellos", codigo=""):
    return {
        "sku": sku,
        "codigo": codigo,
        "nombre": nombre,
        "nombre_familia": familia,
    }


def test_family_products_are_ordered_lineal_then_cr_then_rest():
    items = [
        _item("3", "MB BURLETE PARA PUERTA"),
        _item("2", "CR BURLETE PARA PUERTA"),
        _item("1", "BURLETE PARA PUERTA"),
        _item("4", "BURLETE PARA PUERTA PDQ"),
    ]

    ordered = sorted(items, key=_product_family_sort_key)

    assert [item["sku"] for item in ordered[:2]] == ["1", "2"]
    assert {item["sku"] for item in ordered[2:]} == {"3", "4"}


def test_marker_in_code_prevents_product_from_being_lineal():
    items = [
        _item("SKU-PDQ-1", "BURLETE PARA PUERTA"),
        _item("SKU-BASE-1", "BURLETE PARA PUERTA"),
    ]

    ordered = sorted(items, key=_product_family_sort_key)

    assert [item["sku"] for item in ordered] == ["SKU-BASE-1", "SKU-PDQ-1"]


def test_pack_in_description_is_sorted_as_cr():
    items = [
        _item("2", "PACK TARUGOS 8 MM"),
        _item("1", "TARUGOS 8 MM"),
        _item("3", "TARUGOS 8 MM PDQ"),
    ]

    ordered = sorted(items, key=_product_family_sort_key)

    assert [item["sku"] for item in ordered] == ["1", "2", "3"]


def test_sheet_names_are_valid_limited_and_unique():
    used = set()
    first = _safe_sheet_name("Ventanas/Correderas: formato muy extenso", used)
    second = _safe_sheet_name("Ventanas/Correderas: formato muy extenso", used)

    assert len(first) <= 31
    assert "/" not in first and ":" not in first
    assert first != second
    assert len(second) <= 31


def test_exact_duplicate_export_blocks_are_removed_only_once():
    first = {"sku": "100", "nombre": "Producto", "stock": 10}
    duplicate = dict(first)
    changed = {**first, "stock": 11}

    assert _deduplicate_export_data([first, duplicate, changed]) == [first, changed]


def test_purchase_coverage_and_green_duration_are_separate():
    coverage, arrival_duration = _calcular_coberturas_compra_export(
        total_4_semanas=404,
        compra_sugerida=2256,
        stock_llegada=1,
    )

    assert coverage == 5.58
    assert arrival_duration == 0.0


def test_each_family_has_one_unique_color_per_sheet():
    items = [
        {"sku": "L1", "tiene_familia": True, "clave_familia": "FAM:A"},
        {"sku": "CR1", "tiene_familia": True, "clave_familia": "FAM:A"},
        {"sku": "L2", "tiene_familia": True, "clave_familia": "FAM:B"},
    ]
    _assign_family_colors(items)

    assert items[0]["familia_color"] == items[1]["familia_color"]
    assert items[0]["familia_color"] != items[2]["familia_color"]


def test_current_month_uses_previous_year_in_label():
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 13)

    with patch("api.routes.sop.date", FixedDate):
        month_map = _get_mes_map()

    november = next(item for item in month_map if item[0] == 11)
    assert november[3] == 2026  # columna consultada en BD
    assert november[4] == 2025  # anio real mostrado en la cabecera


def test_inventory_finds_stock_un_when_column_moves(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "inventario.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "INVENTARIO ACTUAL "
    worksheet.append(["REPORTE DE INVENTARIO"])
    worksheet.append(["COD CAJA", "SKU", "NOMBRE", "STOCK UN"])
    worksheet.append(["CAJA-1", "10001", "Producto A", 37])
    workbook.save(path)

    inventory = _read_inventario_excel(path)

    assert inventory.to_dict(orient="records") == [
        {"sku": "10001", "stock_act": 37}
    ]


def test_cr_family_block_contains_full_calculation_box():
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    data = {
        "tiene_familia": True,
        "formato_compra": "CR",
        "nombre_familia": "Familia Sellos",
        "prioridad_planificacion": 2,
        "inv_u": 100,
        "tot4s": 20,
        "demanda_espera_4_meses": 80,
        "transito_confirmado_4_meses": 10,
        "maquila_recibida_4_meses": 0,
        "maquila_destinada_4_meses": 25,
        "deficit_espera_4_meses": 0,
        "stock_estimado_llegada": 5,
        "target_meses": 4.2,
        "crecimiento_compra_pct": 12.5,
        "umbral_crecimiento_compra_pct": 10.0,
        "crecimiento_compra_detectado": True,
        "meses_extra_por_crecimiento": 1.0,
        "ajuste_ano_nuevo_chino_aplicado": True,
        "meses_extra_ano_nuevo_chino": 1.0,
        "obj": 108,
        "sug_bruta": 103,
        "ue": 12,
        "compra": 108,
        "familia_compra_total": 240,
    }

    _poblar_caja_calculo_cr(worksheet, 1, data)

    assert worksheet["N1"].value == "C\u00c1LCULO COMPRA FAMILIA - CR"
    assert "Demanda en espera (4 meses): 80 uds" in worksheet["N2"].value
    assert "Compra final: 108 uds" in worksheet["N2"].value
    assert "Crecimiento 4 semanas vs promedio 5 meses: 12.5%" in worksheet["N2"].value
    assert "Umbral para sumar mes extra: 10.0%" in worksheet["N2"].value
    assert "Mes extra por crecimiento: 1.0" in worksheet["N2"].value
    assert "Mes extra por Año Nuevo Chino (compras Nov-Dic): 1.0" in worksheet["N2"].value
    assert "N1:R1" in {str(item) for item in worksheet.merged_cells.ranges}
    assert "N2:R16" in {str(item) for item in worksheet.merged_cells.ranges}


def test_non_cr_block_removes_copied_cr_box():
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    _poblar_caja_calculo_cr(
        worksheet,
        1,
        {"tiene_familia": True, "formato_compra": "CR"},
    )
    copiar_bloque(worksheet, 1, 16, 17)
    _poblar_caja_calculo_cr(
        worksheet,
        17,
        {"tiene_familia": True, "formato_compra": "LINEAL"},
    )

    assert worksheet["N17"].value is None
    assert "N17:R17" not in {str(item) for item in worksheet.merged_cells.ranges}
    assert "N18:R32" not in {str(item) for item in worksheet.merged_cells.ranges}


def test_lineal_family_block_contains_aggregated_summary():
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    _poblar_caja_resumen_lineal(
        worksheet,
        1,
        {
            "tiene_familia": True,
            "formato_compra": "LINEAL",
            "nombre_familia": "Familia Burletes",
            "ventas_semanales_familia": 15,
            "ventas_4_semanas_familia": 60,
            "stock_familia": 150,
            "duracion_stock_familia_meses": 2.5,
            "cajas_esperadas_mes_familia": 20,
        },
    )

    assert worksheet["N1"].value == "RESUMEN FAMILIA - LINEAL"
    assert "Ventas semanales familia: 15.00 uds" in worksheet["N2"].value
    assert "Stock total familia: 150 uds" in worksheet["N2"].value
    assert "Duración stock familiar: 2.50 meses" in worksheet["N2"].value
    assert "Cajas esperadas por mes: 20.00 cajas" in worksheet["N2"].value


def test_family_metrics_sum_members_and_convert_sell_in_to_boxes():
    import pandas as pd

    month_map = _get_mes_map()
    rows = []
    for sku, code, ump, sell_in in [
        ("L1", "100", 10, 100),
        ("CR1", "101", 5, 50),
    ]:
        row = {"sku": sku, "codigo_femaco": code, "ump": ump}
        for _month, _name, abbreviation, db_year, _label_year in month_map:
            row[f"sellin_{abbreviation}_{db_year}"] = sell_in
        rows.append(row)

    family = {
        "familia_skus": [
            {"sku": "L1", "codigo_femaco": "100", "ritmo_mensual": 40, "descontinuado": False},
            {"sku": "CR1", "codigo_femaco": "101", "ritmo_mensual": 20, "descontinuado": False},
        ],
        "stock_bruto_familia": 150,
    }
    families = {"100": family, "101": family}

    _enriquecer_metricas_familia(families, pd.DataFrame(rows))

    assert family["ventas_semanales_familia"] == 15
    assert family["ventas_4_semanas_familia"] == 60
    assert family["duracion_stock_familia_meses"] == 2.5
    assert family["cajas_esperadas_mes_familia"] == 20
    assert family["codigo_orden_familia"] == "100"


def test_purchase_date_is_lead_time_before_stockout():
    assert _calcular_fecha_compra("2027-05-21") == date(2027, 1, 21)


def test_export_block_uses_f_g_h_purchase_roles_and_duration_labels():
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    data = {
        "sku": "SKU-1", "codigo": "100", "nombre": "Producto", "estado": "ACTIVO", "ue": 10,
        "inv_u": 100, "inv_c": 10, "tra_u": 0, "tra_c": 0, "hc_u": 50, "hc_c": 5,
        "max_so": 100, "max_si": 120, "duracion_al_arribo_4_semanas": 3.2,
        "s1": 10, "s2": 10, "s3": 10, "s4": 10, "tot4s": 40, "cob": 2.5, "obj": 200,
        "anio_labels": [f"Mes {index}" for index in range(12)],
        "sell_out": [0] * 12, "sell_in": [0] * 12,
        "tiene_familia": False, "stock_familia": 100, "sug_bruta": 100, "compra": 100,
        "compra_actual": 100, "compra_proxima": 0, "fecha_compra": date(2026, 11, 21),
        "cobertura_compra_4_semanas": 2.5, "quiebre": "2027-03-21", "motivo": "Prueba",
        "obs": "", "formato_compra": "LINEAL",
    }

    poblar_bloque(worksheet, 1, data)

    assert worksheet["F6"].value == "Compra Soraya"
    assert worksheet["F7"].value == 100
    assert worksheet["F8"].value == "21-11-2026"
    assert worksheet["E8"].value == "ETA compra"
    assert worksheet["G6"].value == "Próxima compra"
    assert worksheet["G7"].value == "-"
    assert worksheet["H6"].value == "Extra manual"
    assert worksheet["H7"].value is None
    assert worksheet["G11"].value == "Duración actual"
    assert worksheet["J10"].value == "Duración proyectada"
    assert worksheet["L9"].value == "Duración"
    assert worksheet["F6"].fill.fgColor.rgb.endswith("F4B183")
