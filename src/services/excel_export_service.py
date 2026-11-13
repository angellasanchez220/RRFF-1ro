import io
import math
import copy
import re
import unicodedata
from pathlib import Path
from datetime import date
from sqlalchemy import text
import pandas as pd
import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from api.db import engine
from api.routes.sop import _get_mes_map, _get_semanas_fact_ventas

CATEGORY_SHEET_MAP = {
    "CINTAS": "Cintas",
    "MONTAJE": "Montaje",
    "TORNILLOS": "Tornillos",
    "SELLOS": "Sellos",
    "SOBERBIO": "Soberbio",
    "GANCHOS": "Ganchos",
    "FIELTROS": "Fieltros",
    "SEGURIDAD": "Seguridad",
    "DEMARCATORIA": "Demarcatoria",
    "CLAVOS": "Clavos"
}

PRESENTATION_MARKERS = ("PDQ", "CR", "MB")


def _normalize_sort_text(value) -> str:
    """Normaliza texto para ordenar sin depender de mayusculas ni tildes."""
    if value is None or (not isinstance(value, (list, dict, tuple, set)) and pd.isna(value)):
        value = ""
    text_value = str(value).strip().upper()
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text_value)
        if unicodedata.category(char) != "Mn"
    )


def _presentation_markers(data: dict) -> set[str]:
    """Detecta PDQ/CR/MB en codigos o en los extremos de la descripcion."""
    codes = " ".join(
        _normalize_sort_text(data.get(field))
        for field in ("sku", "codigo")
    )
    description = _normalize_sort_text(data.get("nombre"))
    markers = {marker for marker in PRESENTATION_MARKERS if marker in codes}

    for marker in PRESENTATION_MARKERS:
        boundary_pattern = rf"(?:^{marker}(?:\W|$)|(?:^|\W){marker}$)"
        if re.search(boundary_pattern, description):
            markers.add(marker)

    return markers


def _product_family_sort_key(data: dict):
    """Agrupa por familia y ordena Lineal, CR y luego el resto."""
    from src.services.maquila_service import detectar_formato_producto

    format_name = data.get("formato_compra") or detectar_formato_producto(
        data.get("codigo"),
        data.get("nombre"),
    )
    presentation_rank = {"LINEAL": 0, "CR": 1}.get(format_name, 2)

    family_key = _normalize_sort_text(
        data.get("nombre_familia") or data.get("sku") or data.get("codigo")
    )
    return (
        family_key,
        presentation_rank,
        _normalize_sort_text(data.get("nombre")),
        _normalize_sort_text(data.get("sku")),
    )


def _safe_sheet_name(value, used_names: set[str]) -> str:
    """Crea un nombre de hoja valido, de hasta 31 caracteres y sin duplicados."""
    base = re.sub(r"[\\/*?:\[\]]", "-", str(value or "SIN SUBCATEGORIA").strip())
    base = re.sub(r"\s+", " ", base).strip(" '") or "SIN SUBCATEGORIA"
    base = base[:31]
    candidate = base
    sequence = 2

    while candidate.casefold() in used_names:
        suffix = f" ({sequence})"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        sequence += 1

    used_names.add(candidate.casefold())
    return candidate

def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f):
            return default
        return f
    except:
        return default


def _safe_text(value, default="") -> str:
    if value is None or pd.isna(value):
        return default
    text_value = str(value).strip()
    return text_value or default

def _safe_int(v, default=0):
    return int(round(_safe_float(v, default)))

def get_sku_export_data(sku: str, familias_map: dict = None) -> dict:
    """Extrae la informaci\u00f3n consolidada de un SKU para exportaci\u00f3n a Excel."""
    with engine.connect() as conn:
        df_sop = pd.read_sql(text("""
            SELECT *
            FROM planificacion_sop
            WHERE (sku = :s OR codigo_femaco = :s)
              AND UPPER(TRIM(COALESCE(estado, '')))
                  NOT IN ('DESCONTINUADO', 'DESCONTINUADOS', 'INACTIVO')
        """), conn, params={"s": sku})
        if df_sop.empty:
            return None
        row_sop = df_sop.iloc[0].to_dict()
        
        # Obtener el SKU real canónico desde la base de datos (por si se buscó por código femaco)
        real_sku = str(row_sop.get("sku", sku))
        codigo_value = row_sop.get("codigo_femaco")
        real_codigo = "" if pd.isna(codigo_value) else str(codigo_value).strip().upper()

        sem_map = _get_semanas_fact_ventas(conn)
        ventas_sku = sem_map.get(real_sku, {})

        df_tr = pd.read_sql(text("""
            SELECT codigo_envio, cantidad, COALESCE(eta_ajustada, fecha_disponibilidad_real) as eta
            FROM control_embarques
            WHERE (sku = :s OR codigo_femaco = :s) AND estado IN ('EN_TRANSITO','EN_AFORO','RETRASADO')
            ORDER BY fecha_eta ASC NULLS LAST
            LIMIT 3
        """), conn, params={"s": sku})
        pedidos = df_tr.to_dict(orient="records")

        total_transito = _safe_int(row_sop.get("cantidad_transito"))

        obs_row = conn.execute(text("SELECT observacion FROM sku_observaciones WHERE sku=:s"), {"s": real_sku}).fetchone()
        observacion = obs_row.observacion if obs_row and obs_row.observacion else ""
        
        # Familia de Reemplazo
        if familias_map and real_codigo in familias_map and len(familias_map[real_codigo]["familia_skus"]) > 1:
            fam = familias_map[real_codigo]
            comp_strs = []
            for c in fam["familia_skus"]:
                nt_str = " [NO TRANSFORMABLE]" if c.get("no_transformable") else ""
                comp_strs.append(
                    f"CÓD {c['codigo_femaco']} / SKU {c['sku']} "
                    f"Stock {int(c['stock_act'])} / RV {int(c['ritmo_mensual'])}{nt_str}"
                )
            fam_str = f"Familia SKU:\n" + "\n".join(comp_strs) + f"\n\nStock bruto familia: {int(fam['stock_bruto_familia'])} uds."
            
            reemplazos = [r['sku'] for r in fam["reemplazos_validos"]]
            if reemplazos:
                fam_str += f"\n\nReemplazos válidos para CÓD {real_codigo}:\n" + ", ".join(reemplazos)
            
            if observacion:
                observacion = observacion + "\n\n" + fam_str
            else:
                observacion = fam_str

    ue = _safe_float(row_sop.get("ump"), 1.0)
    if ue == 0:
        ue = 1.0

    inv_u = _safe_int(row_sop.get("stock_act"))
    hc_u = _safe_int(ventas_sku.get("stock_fisico_matrix"))
    
    mes_map = _get_mes_map()
    sell_out = []
    sell_in = []
    meses_nombres = []
    max_so = 0
    max_si = 0

    for mes_num, nombre, abrev, yr_db, yr_label in mes_map:
        col_so = f"sellout_{abrev}_{yr_db}"
        col_si = f"sellin_{abrev}_{yr_db}"
        so_val = _safe_int(row_sop.get(col_so))
        si_val = _safe_int(row_sop.get(col_si))
        sell_out.append(so_val)
        sell_in.append(si_val)
        meses_nombres.append(f"{nombre[:3]} {yr_label}")
        if so_val > max_so: max_so = so_val
        if si_val > max_si: max_si = si_val

    purchase_trace = (
        f"Formato: {_safe_text(row_sop.get('formato_compra'), 'LINEAL')} | "
        f"Demanda espera 4 meses: {_safe_int(row_sop.get('demanda_espera_4_meses'))} | "
        f"Maquila recibida/destinada: "
        f"{_safe_int(row_sop.get('maquila_recibida_4_meses'))}/"
        f"{_safe_int(row_sop.get('maquila_destinada_4_meses'))} | "
        f"Stock estimado llegada: {_safe_int(row_sop.get('stock_estimado_llegada'))} | "
        f"Target: {_safe_int(row_sop.get('stock_objetivo'))}"
    )
    purchase_reason = str(
        row_sop.get("explicacion_compra_dinamica")
        or row_sop.get("explicacion_compra")
        or ""
    ).strip()

    data = {
        "sku": real_sku,
        "categoria": _safe_text(row_sop.get("categoria"), "SIN CATEGORIA").upper(),
        "subcategoria": _safe_text(row_sop.get("subcategoria"), "SIN SUBCATEGORIA"),
        "codigo": _safe_text(row_sop.get("codigo_femaco")),
        "nombre": _safe_text(row_sop.get("nombre_producto")),
        "estado": _safe_text(row_sop.get("estado")),
        "ue": ue,
        
        "anio_labels": meses_nombres,
        "sell_out": sell_out,
        "sell_in": sell_in,
        
        "inv_u": inv_u,
        "inv_c": round(inv_u / ue, 2),
        
        "tra_u": total_transito,
        "tra_c": round(total_transito / ue, 2),
        
        "hc_u": hc_u,
        "hc_c": round(hc_u / ue, 2),
        
        "pedidos": pedidos,
        
        "max_so": max_so,
        "max_si": max_si,
        
        "s1": _safe_int(ventas_sku.get("sem1_uds")),
        "s2": _safe_int(ventas_sku.get("sem2_uds")),
        "s3": _safe_int(ventas_sku.get("sem3_uds")),
        "s4": _safe_int(ventas_sku.get("sem4_uds")),
        "tot4s": _safe_int(ventas_sku.get("total_4_sem_verificado")),
        
        "obj": _safe_int(row_sop.get("stock_objetivo")),
        "sug_bruta": _safe_int(row_sop.get("sugerencia_bruta")),
        "compra": _safe_int(row_sop.get("sugerencia_final")),
        "cob": round(float(row_sop.get("stock_act") or 0) / _safe_float(row_sop.get("sug_ritmo_mensual")), 1) if _safe_float(row_sop.get("sug_ritmo_mensual")) > 0 else 999.0,
        "quiebre": str(row_sop.get("fecha_estimada_quiebre") or ""),
        "motivo": f"{purchase_trace}. {purchase_reason}".strip(),
        "formato_compra": _safe_text(row_sop.get("formato_compra"), "LINEAL"),
        "demanda_espera_4_meses": _safe_int(row_sop.get("demanda_espera_4_meses")),
        "maquila_recibida_4_meses": _safe_int(row_sop.get("maquila_recibida_4_meses")),
        "maquila_destinada_4_meses": _safe_int(row_sop.get("maquila_destinada_4_meses")),
        "stock_estimado_llegada": _safe_int(row_sop.get("stock_estimado_llegada")),
        "familia_compra_total": _safe_int(row_sop.get("familia_compra_total")),
        "obs": observacion,
        "tiene_familia": (familias_map is not None and real_codigo in familias_map and len(familias_map[real_codigo].get("familia_skus", [])) > 1),
        "stock_familia": int(familias_map[real_codigo].get("stock_bruto_familia", inv_u)) if (familias_map and real_codigo in familias_map) else inv_u,
        "nombre_familia": familias_map[real_codigo].get("nombre_familia", "") if (familias_map and real_codigo in familias_map and len(familias_map[real_codigo].get("familia_skus", [])) > 1) else ""
    }
    return data

def copiar_bloque(ws: Worksheet, fila_origen_inicio: int, fila_origen_fin: int, fila_destino_inicio: int):
    offset = fila_destino_inicio - fila_origen_inicio
    
    for row in range(fila_origen_inicio, fila_origen_fin + 1):
        if row in ws.row_dimensions:
            ws.row_dimensions[row + offset].height = ws.row_dimensions[row].height

        for col in range(1, ws.max_column + 1):
            source_cell = ws.cell(row=row, column=col)
            target_cell = ws.cell(row=row + offset, column=col)

            target_cell.value = source_cell.value
            
            if source_cell.has_style:
                target_cell.font = copy.copy(source_cell.font)
                target_cell.border = copy.copy(source_cell.border)
                target_cell.fill = copy.copy(source_cell.fill)
                target_cell.number_format = copy.copy(source_cell.number_format)
                target_cell.protection = copy.copy(source_cell.protection)
                target_cell.alignment = copy.copy(source_cell.alignment)

    merges_to_add = []
    for merge_range in list(ws.merged_cells.ranges):
        if fila_origen_inicio <= merge_range.min_row <= fila_origen_fin:
            min_col, min_row, max_col, max_row = merge_range.bounds
            new_merge = f"{openpyxl.utils.get_column_letter(min_col)}{min_row + offset}:{openpyxl.utils.get_column_letter(max_col)}{max_row + offset}"
            merges_to_add.append(new_merge)
            
    for nm in merges_to_add:
        ws.merge_cells(nm)

def poblar_bloque(ws: Worksheet, fila_inicio: int, data: dict):
    def set_val(col, row_offset, val):
        ws.cell(row=fila_inicio + row_offset, column=col, value=val)

    set_val(2, 0, data["sku"])
    set_val(3, 0, data["codigo"])
    set_val(4, 0, data["nombre"])
    set_val(7, 0, data["estado"])
    set_val(9, 0, data["ue"])
    set_val(10, 0, "Maquilable:" if data.get("tiene_familia") else "")
    set_val(11, 0, "SÍ" if data.get("tiene_familia") else "NO")
    set_val(12, 0, "Stock Familia:" if data.get("tiene_familia") else "")
    set_val(13, 0, data.get("stock_familia", "") if data.get("tiene_familia") else "")
    
    set_val(2, 6, data["inv_u"])
    set_val(3, 6, data["inv_c"])
    set_val(2, 7, data["tra_u"])
    set_val(3, 7, data["tra_c"])
    set_val(2, 8, data["hc_u"])
    set_val(3, 8, data["hc_c"])
    
    set_val(10, 6, data["max_so"])
    set_val(10, 7, data["max_si"])
    set_val(10, 10, data["cob"])
    
    set_val(2, 11, data["s1"])
    set_val(3, 11, data["s2"])
    set_val(4, 11, data["s3"])
    set_val(5, 11, data["s4"])
    set_val(6, 11, data["tot4s"])
    set_val(7, 10, "Duración")
    set_val(7, 11, data["cob"])
    set_val(8, 10, "Objetivo")
    set_val(8, 11, data["obj"])

    for i, label in enumerate(data["anio_labels"]):
        set_val(2 + i, 1, label)
        
    for i in range(12):
        set_val(2 + i, 2, data["sell_out"][i])
        set_val(2 + i, 3, data["sell_in"][i])

    for col_idx in [6, 7, 8]:
        for row_offset in [5, 6, 7, 8]:
            set_val(col_idx, row_offset, "")

    pedidos = data["pedidos"]
    for i in range(min(3, len(pedidos))):
        col_idx = 6 + i  # F, G, H
        set_val(col_idx, 5, pedidos[i]["codigo_envio"])
        set_val(col_idx, 6, pedidos[i]["cantidad"])
        eta = pedidos[i]["eta"]
        if pd.notna(eta) and eta and str(eta) != "NaT":
            try:
                set_val(col_idx, 7, pd.to_datetime(eta).strftime("%d-%m-%Y"))
            except Exception:
                set_val(col_idx, 7, str(eta)[:10])
        else:
            set_val(col_idx, 7, "-")
        set_val(col_idx, 8, "-")  # Duración no disponible

    # Pintar cabecera (primera fila del bloque) si tiene familia
    if data.get("tiene_familia"):
        from openpyxl.styles import PatternFill
        familia_fill = PatternFill(start_color="D2B4DE", end_color="D2B4DE", fill_type="solid")
        # Columnas A a M (1 a 13)
        for col in range(1, 14):
            celda = ws.cell(row=fila_inicio, column=col)
            celda.fill = familia_fill

    # Sugerencia bruta
    set_val(12, 6, "Sugerencia bruta")
    sug_bruta = data.get("sug_bruta", 0)
    set_val(13, 6, f"{sug_bruta} unidades" if sug_bruta > 0 else "-")
    
    # Sugerencia final (ajustada a UMP)
    set_val(12, 7, "Sugerencia final (ajustada a UMP)")
    sug_final = data.get("compra", 0)
    set_val(13, 7, f"{sug_final} unidades" if sug_final > 0 else "-")
    
    # Cobertura
    set_val(12, 8, "Cobertura")
    cob = data.get("cob")
    if pd.notna(cob) and cob < 999.0:
        set_val(13, 8, f"{str(cob).replace('.', ',')} meses")
    else:
        set_val(13, 8, "+10 meses" if pd.notna(cob) else "-")
        
    # Quiebre
    set_val(12, 9, "Quiebre")
    quiebre = data.get("quiebre")
    if pd.notna(quiebre) and quiebre and str(quiebre) != "NaT":
        try:
            set_val(13, 9, pd.to_datetime(quiebre).strftime("%d-%m-%Y"))
        except Exception:
            set_val(13, 9, str(quiebre)[:10])
    else:
        set_val(13, 9, "-")
        
    # Motivo
    set_val(12, 10, "Motivo")
    set_val(13, 10, data["motivo"] if data["motivo"] else "-")
    
    # Observación
    set_val(12, 11, "Observación")
    set_val(13, 11, data["obs"] if data["obs"] else "-")


def generar_excel_skus(skus: list[str]) -> bytes:
    if not skus:
        raise ValueError("Lista de SKUs vac\u00eda")

    from src.services.maquila_service import (
        build_maquila_families,
        build_product_lookup_by_internal_code,
    )
    with engine.connect() as conn:
        df_lookup = pd.read_sql(text("SELECT codigo_femaco, sku, nombre_producto, stock_act, total_4_sem_verificado FROM planificacion_sop"), conn)
    lookup_dict = build_product_lookup_by_internal_code(
        df_lookup,
        ritmo_col="total_4_sem_verificado",
    )
    
    with engine.connect() as conn:
        familias_map = build_maquila_families(conn, lookup_dict)

    datos_skus = []
    faltantes = []
    for s in skus:
        d = get_sku_export_data(s, familias_map=familias_map)
        if not d:
            faltantes.append(s)
        else:
            datos_skus.append(d)
            
    if faltantes:
        raise ValueError(f"Los siguientes SKUs no se encontraron o no tienen datos: {', '.join(faltantes)}")

    # Agrupar por subcategoria. Se conserva una etiqueta legible y se usa una
    # clave normalizada para evitar hojas duplicadas por diferencias de tildes,
    # mayusculas o espacios.
    agrupados = {}
    for d in datos_skus:
        subcategoria = d.get("subcategoria") or "SIN SUBCATEGORIA"
        subcategoria_key = _normalize_sort_text(subcategoria) or "SIN SUBCATEGORIA"
        if subcategoria_key not in agrupados:
            agrupados[subcategoria_key] = {
                "label": str(subcategoria).strip() or "SIN SUBCATEGORIA",
                "items": [],
            }
        agrupados[subcategoria_key]["items"].append(d)
        
    # Mantener juntas las familias de maquila y, dentro de cada familia,
    # presentar primero Lineal, despues CR y finalmente PDQ/MB/resto.
    for group in agrupados.values():
        group["items"].sort(key=_product_family_sort_key)
        
    base_dir = Path(__file__).resolve().parent.parent
    template_path = base_dir / "templates" / "RRFF_AS_PLANTILLA_APP.xlsx"
    if not template_path.exists():
        raise FileNotFoundError(f"Plantilla no encontrada en {template_path}")

    wb = openpyxl.load_workbook(template_path)
    ws_plantilla = wb["PLANTILLA"]
    TAMANO_BLOQUE = 16

    # Ordenar subcategorias alfabeticamente para las hojas.
    subcategorias_ordenadas = sorted(agrupados.keys())
    used_sheet_names = set()
    
    for subcategoria_key in subcategorias_ordenadas:
        group = agrupados[subcategoria_key]
        sheet_name = _safe_sheet_name(group["label"], used_sheet_names)
        ws_subcategoria = wb.copy_worksheet(ws_plantilla)
        ws_subcategoria.title = sheet_name
        
        # Poblar bloques en la hoja de la subcategoria.
        for i, data in enumerate(group["items"]):
            fila_inicio = 1 + (i * TAMANO_BLOQUE)
            
            if i > 0:
                copiar_bloque(ws_subcategoria, fila_origen_inicio=1, fila_origen_fin=TAMANO_BLOQUE, fila_destino_inicio=fila_inicio)
                
            poblar_bloque(ws_subcategoria, fila_inicio, data)
            
    # Eliminar plantillas originales
    if "PLANTILLA" in wb.sheetnames:
        del wb["PLANTILLA"]
    if "MAPEO_DEV" in wb.sheetnames:
        del wb["MAPEO_DEV"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def generate_excel_for_sku(sku: str) -> bytes:
    """Wrapper para mantener compatibilidad con el Hito 1."""
    return generar_excel_skus([sku])

def generar_excel_todos_skus() -> bytes:
    """Genera un archivo Excel único conteniendo todos los SKUs de planificacion_sop en orden alfanumérico."""
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT sku
            FROM planificacion_sop
            WHERE UPPER(TRIM(COALESCE(estado, '')))
                  NOT IN ('DESCONTINUADO', 'DESCONTINUADOS', 'INACTIVO')
            ORDER BY sku ASC
        """), conn)
        
    skus_totales = df["sku"].dropna().tolist()
    if not skus_totales:
        raise ValueError("No se encontraron SKUs en planificacion_sop")
        
    return generar_excel_skus(skus_totales)

