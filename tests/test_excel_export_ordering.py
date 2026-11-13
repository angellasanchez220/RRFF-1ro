from datetime import date
from unittest.mock import patch

from api.routes.sop import _get_mes_map
from src.services.excel_export_service import (
    _product_family_sort_key,
    _safe_sheet_name,
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


def test_sheet_names_are_valid_limited_and_unique():
    used = set()
    first = _safe_sheet_name("Ventanas/Correderas: formato muy extenso", used)
    second = _safe_sheet_name("Ventanas/Correderas: formato muy extenso", used)

    assert len(first) <= 31
    assert "/" not in first and ":" not in first
    assert first != second
    assert len(second) <= 31


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

