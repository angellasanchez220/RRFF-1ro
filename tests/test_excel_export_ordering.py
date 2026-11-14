from datetime import date
from unittest.mock import patch

from api.routes.sop import _get_mes_map
from src.services.excel_export_service import (
    _product_family_sort_key,
    _assign_family_colors,
    _deduplicate_export_data,
    _safe_sheet_name,
    _poblar_caja_calculo_cr,
    copiar_bloque,
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
        "crecimiento_compra_detectado": True,
        "meses_extra_por_crecimiento": 1.0,
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
    assert "Mes extra por crecimiento: 1.0" in worksheet["N2"].value
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
