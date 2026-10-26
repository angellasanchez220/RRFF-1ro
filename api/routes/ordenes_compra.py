"""
api/routes/ordenes_compra.py — Módulo de Órdenes de Compra y Auditoría de Despacho
================================================================================
Permite subir Órdenes de Compra (OCs) en dos etapas:
  1. PEDIDO (Opcional): registro inicial de lo solicitado por el cliente/empresa.
  2. ENTREGA (Despacho): auditoría de cumplimiento real vs lo pedido.

Detecta automáticamente:
  - Productos no despachados (despacho = 0).
  - Despachos parciales (despacho < pedido).
  - Desbalance Familiar: si en una familia un producto se despachó pero otro(s) no.
  - Quiebres históricos y tiempo transcurrido (en días) hasta que se volvió a vender/despachar.
"""

import io
import re
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from decimal import Decimal
import pandas as pd
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()


def _normalize_col_name(c: str) -> str:
    c = str(c).lower().strip()
    c = re.sub(r'[\s_]+', '_', c)
    c = re.sub(r'[^\w_]', '', c)
    return c


def _find_column(columns: List[str], candidate_patterns: List[str]) -> Optional[str]:
    for pat in candidate_patterns:
        regex = re.compile(pat, re.IGNORECASE)
        for c in columns:
            if regex.search(str(c).strip()):
                return c
    return None


def _parse_date(val: Any) -> Optional[date]:
    if pd.isna(val) or val is None or str(val).strip() == '':
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    s = str(val).strip()
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}', s):
            dt = pd.to_datetime(s, format='mixed', errors='coerce')
        else:
            dt = pd.to_datetime(s, errors='coerce', dayfirst=True)
        if pd.notna(dt):
            return dt.date()
    except Exception:
        pass
    return None


def _detect_quantity_columns(cols: List[str]):
    """
    Detecta columnas de cantidad pedida y despachada.
    Soporta exports de portales retail (Sodimac/B2B) donde pandas renombra 'Unidades' duplicadas a 'Unidades' y 'Unidades.1'.
    """
    # Caso 1: Columnas duplicadas que pandas renombra con .1 (p.ej. Unidades y Unidades.1)
    unidades_cols = [c for c in cols if re.match(r'^unidades(?:\.0)?$', str(c).strip(), re.IGNORECASE)]
    unidades_1_cols = [c for c in cols if re.match(r'^unidades\.[1-9]\d*$', str(c).strip(), re.IGNORECASE)]
    if unidades_cols and unidades_1_cols:
        return unidades_cols[0], unidades_1_cols[0]

    cant_cols = [c for c in cols if re.match(r'^cantidad(?:\.0)?$', str(c).strip(), re.IGNORECASE)]
    cant_1_cols = [c for c in cols if re.match(r'^cantidad\.[1-9]\d*$', str(c).strip(), re.IGNORECASE)]
    if cant_cols and cant_1_cols:
        return cant_cols[0], cant_1_cols[0]

    # Caso 2: Nombres explícitos de cantidades
    col_ped = None
    for pat in [
        r'cant(?:idad)?[_\s]*(?:pedida|solicitada|comprada)',
        r'unidades[_\s]*(?:pedidas|compradas|solicitadas)',
        r'^pedido$', r'^solicitado$', r'^solicitada$'
    ]:
        for c in cols:
            if re.search(pat, str(c).strip(), re.IGNORECASE):
                col_ped = c
                break
        if col_ped:
            break

    col_desp = None
    for pat in [
        r'cant(?:idad)?[_\s]*(?:despachada|entregada|recibida|recepcionada)',
        r'unidades[_\s]*(?:despachadas|entregadas|recibidas|recepcionadas)',
        r'^despacho$', r'^entregado$', r'^recibido$', r'^recepcionado$'
    ]:
        for c in cols:
            if re.search(pat, str(c).strip(), re.IGNORECASE):
                col_desp = c
                break
        if col_desp:
            break

    if not col_ped and not col_desp:
        if unidades_cols:
            col_ped = unidades_cols[0]
        elif cant_cols:
            col_ped = cant_cols[0]

    return col_ped, col_desp


def _read_file_to_df(content: bytes, filename: str) -> pd.DataFrame:
    """Lee archivos Excel o CSV de portales B2B con detección automática de separador, codificación y fila de cabecera."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".csv"):
        for sep in [";", ",", "\t"]:
            for enc in ["latin-1", "utf-8", "utf-8-sig"]:
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=enc)
                    if len(df.columns) > 2:
                        return df
                except Exception:
                    continue
        return pd.read_csv(io.BytesIO(content))
    else:
        try:
            df = pd.read_excel(io.BytesIO(content))
        except Exception:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")

        # Verificar si la cabecera real está más abajo (filas de título o metadatos)
        expected_pats = [r"sku", r"orden", r"unidades", r"cant", r"vin", r"item", r"c[oó]digo"]
        matched = sum(1 for c in df.columns if any(re.search(p, str(c), re.IGNORECASE) for p in expected_pats))
        if matched == 0 and len(df) > 0:
            for header_idx in range(1, min(10, len(df))):
                candidate_cols = [str(x) for x in df.iloc[header_idx - 1].tolist()]
                m = sum(1 for c in candidate_cols if any(re.search(p, c, re.IGNORECASE) for p in expected_pats))
                if m >= 2:
                    try:
                        df = pd.read_excel(io.BytesIO(content), header=header_idx)
                        break
                    except Exception:
                        pass
        return df


def _interpret_estado_y_etapa(estado_raw: str, sum_ped: float, sum_desp: float, user_etapa: str):
    """
    Interpreta el estado del portal ('Cursado', 'Recepción', etc.) y define la etapa correspondiente.
    """
    user_etapa = (user_etapa or "AUTO").strip().upper()
    estado_raw_str = str(estado_raw or "").strip()
    e_lower = estado_raw_str.lower()

    if user_etapa in ("PEDIDO", "ENTREGA"):
        # Selección forzada por el usuario
        if estado_raw_str:
            return user_etapa, estado_raw_str.upper()
        return user_etapa, ("CURSADO" if user_etapa == "PEDIDO" else "RECEPCIONADO")

    # Detección Automática (AUTO)
    if estado_raw_str:
        if any(k in e_lower for k in ["cursa", "pend", "vigen", "emit"]):
            return "PEDIDO", "CURSADO"
        elif any(k in e_lower for k in ["recep", "entreg", "cerrad", "factur", "cumpli"]):
            return "ENTREGA", "RECEPCIONADO"
        elif any(k in e_lower for k in ["anul", "cancel"]):
            return "PEDIDO", "ANULADO"
        else:
            if sum_desp > 0:
                return "ENTREGA", estado_raw_str.upper()
            else:
                return "PEDIDO", estado_raw_str.upper()

    # Si no hay columna de estado
    if sum_desp > 0:
        return "ENTREGA", "RECEPCIONADO"
    else:
        return "PEDIDO", "CURSADO"


def _load_active_families(conn) -> Dict[str, Dict[str, Any]]:
    """
    Retorna un diccionario {codigo_femaco_or_sku: {"familia_id": int, "nombre_familia": str, "miembros": [codes]}}
    """
    rows = conn.execute(text("""
        SELECT r.id AS familia_id,
               COALESCE(NULLIF(TRIM(r.descripcion), ''), r.sku_maquilable) AS nombre_familia,
               c.sku_componente
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON c.receta_id = r.id
        WHERE r.activa = TRUE
    """)).fetchall()

    fam_members = {}
    for r in rows:
        fid = r.familia_id
        fname = r.nombre_familia
        comp = str(r.sku_componente).strip().upper()
        if fid not in fam_members:
            fam_members[fid] = {"nombre": fname, "miembros": []}
        fam_members[fid]["miembros"].append(comp)

    # Invertir para lookup rápido por código
    lookup = {}
    for fid, data in fam_members.items():
        for m in data["miembros"]:
            lookup[m] = {
                "familia_id": fid,
                "nombre_familia": data["nombre"],
                "miembros": data["miembros"]
            }
    return lookup


def _recalcular_tiempos_recuperacion(conn, skus_afectados: List[str]):
    """
    Para cada SKU afectado, revisa cronológicamente todas las OCs donde hubo quiebre
    y busca la primera OC posterior donde se volvió a despachar (>0), calculando días transcurridos.
    """
    if not skus_afectados:
        return

    query = text("""
        SELECT d.id AS detalle_id, d.numero_oc, d.sku, d.codigo_femaco,
               d.cantidad_pedida, d.cantidad_despachada, d.quiebre_detectado,
               d.fecha_quiebre, r.fecha_entrega, r.fecha_carga
        FROM ordenes_compra_detalle d
        JOIN ordenes_compra_registro r ON d.oc_id = r.id
        WHERE (UPPER(d.sku) = ANY(:skus) OR UPPER(d.codigo_femaco) = ANY(:skus))
          AND r.etapa = 'ENTREGA'
        ORDER BY COALESCE(r.fecha_entrega, r.fecha_carga::date) ASC, d.id ASC
    """)
    skus_upper = [s.strip().upper() for s in skus_afectados if s]
    rows = conn.execute(query, {"skus": skus_upper}).mappings().all()

    history_by_sku = {}
    for r in rows:
        key = str(r["sku"] or r["codigo_femaco"]).strip().upper()
        history_by_sku.setdefault(key, []).append(dict(r))

    for key, items in history_by_sku.items():
        for i, item in enumerate(items):
            if float(item["cantidad_pedida"] or 0) > 0 and float(item["cantidad_despachada"] or 0) == 0:
                fecha_q = item["fecha_entrega"] or (item["fecha_carga"].date() if item["fecha_carga"] else None)
                recuperado_oc = None
                fecha_rec = None
                dias_rec = None

                for next_item in items[i+1:]:
                    if float(next_item["cantidad_despachada"] or 0) > 0:
                        recuperado_oc = next_item["numero_oc"]
                        fecha_rec = next_item["fecha_entrega"] or (next_item["fecha_carga"].date() if next_item["fecha_carga"] else None)
                        if fecha_q and fecha_rec:
                            dias_rec = (fecha_rec - fecha_q).days
                            if dias_rec < 0:
                                dias_rec = 0
                        break

                conn.execute(text("""
                    UPDATE ordenes_compra_detalle
                    SET quiebre_detectado = TRUE,
                        fecha_quiebre = :fq,
                        oc_recuperacion = :oc_rec,
                        fecha_recuperacion = :f_rec,
                        dias_recuperacion_quiebre = :dias
                    WHERE id = :id
                """), {
                    "fq": fecha_q,
                    "oc_rec": recuperado_oc,
                    "f_rec": fecha_rec,
                    "dias": dias_rec,
                    "id": item["detalle_id"]
                })


@router.post("/upload")
async def upload_orden_compra(
    file: UploadFile = File(...),
    etapa: str = Form("AUTO"),
    numero_oc: Optional[str] = Form(None),
    cliente: Optional[str] = Form(""),
    fecha_pedido: Optional[str] = Form(None),
    fecha_entrega: Optional[str] = Form(None),
    authorization: str = Header(None)
):
    """
    Sube y procesa Órdenes de Compra individuales o masivas con historial de varios meses.
    Detecta automáticamente número de OC, etapa ('PEDIDO' vs 'ENTREGA'), estado ('CURSADO' vs 'RECEPCIONADO'),
    consolida por local/tienda al nivel de SKU y calcula auditoría de cumplimiento, quiebres y tiempos de recuperación.
    """
    token = _get_auth_header(authorization)
    user_payload = decode_token(token)
    usuario = user_payload.get("sub") or user_payload.get("username") or "sistema"

    etapa_val = etapa if isinstance(etapa, str) else "AUTO"
    etapa_val = etapa_val.strip().upper()
    if etapa_val not in ("AUTO", "PEDIDO", "ENTREGA"):
        raise HTTPException(status_code=400, detail="La etapa debe ser 'AUTO', 'PEDIDO' o 'ENTREGA'")

    form_oc_num = (numero_oc if isinstance(numero_oc, str) else "").strip()
    form_cliente = (cliente if isinstance(cliente, str) else "").strip()
    form_fecha_ped = fecha_pedido if isinstance(fecha_pedido, str) else None
    form_fecha_ent = fecha_entrega if isinstance(fecha_entrega, str) else None

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    filename = file.filename or "archivo.xlsx"
    try:
        df = _read_file_to_df(content, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}")

    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas con datos")

    cols = list(df.columns)

    # Identificar columnas principales
    col_oc = _find_column(cols, [
        r"^(?:n[úu]mero|nro|n°)[_\s]*(?:oc|compra|orden|pedido)?.*$",
        r"n[úu]mero.*", r"n°.*orden", r"orden[_\s]*compra", r"^oc$", r"^pedido$"
    ])
    col_sku = _find_column(cols, [
        r"^(?:sku|material|item)$", r"sku.*", r"c[oó]digo"
    ])
    col_femaco = _find_column(cols, [
        r"^(?:vin|vendor[_\s]*item[_\s]*number)$",
        r"c[oó]d(?:igo)?[_\s]*femaco", r"c[oó]d(?:igo)?[_\s]*interno", r"^c[oó]digo$"
    ])
    col_nombre = _find_column(cols, [
        r"^(?:nombre|nombre[_\s]*producto|descripci[oó]n|producto|modelo)$",
        r"descripci[oó]n.*"
    ])
    col_estado_oc = _find_column(cols, [
        r"^(?:estado[_\s]*oc|estado|status|situaci[oó]n)$", r"estado.*"
    ])

    col_ped, col_desp = _detect_quantity_columns(cols)

    col_cliente = _find_column(cols, [r"^(?:cliente|comprador|bu)$", r"cliente.*", r"raz[oó]n[_\s]*social"])
    col_bu = _find_column(cols, [r"^bu$", r"bu.*"])
    col_local = _find_column(cols, [r"local", r"sucursal", r"tienda"])
    col_fecha_p = _find_column(cols, [r"fecha.*(?:creaci[oó]n|pedido|emisi[oó]n|compra)", r"fecha.*inic.*", r"fecha[_\s]*oc"])
    col_fecha_e = _find_column(cols, [r"fecha.*(?:entrega|despacho|recepci[oó]n)", r"fecha.*fin.*", r"fecha.*venc.*"])

    if not col_sku and not col_femaco:
        raise HTTPException(status_code=400, detail="No se encontró columna para SKU o Código Interno/VIN.")

    # Agrupar por Orden de Compra si existe columna de OC
    oc_groups = []
    if col_oc:
        # Extraer OCs válidas
        valid_rows = df[df[col_oc].notna() & (df[col_oc].astype(str).str.strip() != '')]
        grouped = valid_rows.groupby(col_oc)
        for val_oc, df_subset in grouped:
            str_oc = str(val_oc).strip()
            # Filtrar cabeceras repetidas si las hubiera
            if str_oc.lower() in ('none', 'nan', 'null', 'n° de orden', 'numero oc', 'orden', 'oc'):
                continue
            oc_groups.append((str_oc, df_subset))

    if not oc_groups:
        # Una sola OC tomada del formulario o del nombre del archivo
        fallback_num = form_oc_num
        if not fallback_num:
            match_fn = re.search(r'(?:OC|ORDEN|PEDIDO)[_\s-]*([A-Za-z0-9_-]+)', filename, re.IGNORECASE)
            fallback_num = match_fn.group(0) if match_fn else filename.rsplit('.', 1)[0]
        oc_groups.append((fallback_num, df))

    processed_results = []
    all_affected_skus = []

    with engine.begin() as conn:
        familias_map = _load_active_families(conn)

        # Catálogo de planificacion_sop para descripciones y cruces
        sop_rows = conn.execute(text("SELECT sku, codigo_femaco, nombre_producto FROM planificacion_sop")).fetchall()
        sop_by_sku = {str(r.sku).strip().upper(): str(r.nombre_producto or '') for r in sop_rows if r.sku}
        sop_by_fem = {str(r.codigo_femaco).strip().upper(): str(r.nombre_producto or '') for r in sop_rows if r.codigo_femaco}
        sku_to_fem = {str(r.sku).strip().upper(): str(r.codigo_femaco or '') for r in sop_rows if r.sku}

        for oc_num, df_oc in oc_groups:
            # 1. Determinar Cliente
            cli = form_cliente
            if not cli:
                if col_bu:
                    vbu = df_oc[col_bu].dropna().astype(str).str.strip()
                    if not vbu.empty and 'SOD' in vbu.iloc[0].upper():
                        cli = "Sodimac Chile"
                if not cli and col_local:
                    vloc = df_oc[col_local].dropna().astype(str).str.strip()
                    if not vloc.empty and vloc.iloc[0].upper().startswith("HC"):
                        cli = "Sodimac / Homecenter"
                if not cli and col_cliente:
                    vcli = df_oc[col_cliente].dropna().astype(str).str.strip()
                    if not vcli.empty:
                        candidate_cli = vcli.iloc[0]
                        if "FEMACO" not in candidate_cli.upper():
                            cli = candidate_cli
                        else:
                            cli = "Sodimac Chile"
            if not cli:
                cli = "Sodimac Chile" if ("SOD" in str(cols) or "HC" in str(cols)) else "Cliente General"

            # 2. Fechas
            f_ped = _parse_date(form_fecha_ped)
            if not f_ped and col_fecha_p:
                vfp = df_oc[col_fecha_p].dropna()
                if not vfp.empty:
                    f_ped = _parse_date(vfp.iloc[0])

            f_ent = _parse_date(form_fecha_ent)
            if not f_ent and col_fecha_e:
                vfe = df_oc[col_fecha_e].dropna()
                if not vfe.empty:
                    f_ent = _parse_date(vfe.iloc[0])

            # 3. Extraer ítems crudos
            raw_items = []
            for idx, row in df_oc.iterrows():
                sku_val = str(row[col_sku]).strip() if col_sku and pd.notna(row.get(col_sku)) else ""
                fem_val = str(row[col_femaco]).strip() if col_femaco and pd.notna(row.get(col_femaco)) else ""
                if not sku_val and not fem_val:
                    continue

                if sku_val and not fem_val and sku_val.upper() in sku_to_fem:
                    fem_val = sku_to_fem[sku_val.upper()]

                nombre_val = ""
                if col_nombre and pd.notna(row.get(col_nombre)):
                    nombre_val = str(row[col_nombre]).strip()
                if not nombre_val:
                    nombre_val = sop_by_sku.get(sku_val.upper()) or sop_by_fem.get(fem_val.upper()) or "Producto sin descripción"

                cant_p = 0.0
                cant_d = 0.0
                if col_ped and pd.notna(row.get(col_ped)):
                    try: cant_p = float(row[col_ped])
                    except Exception: cant_p = 0.0

                if col_desp and pd.notna(row.get(col_desp)):
                    try: cant_d = float(row[col_desp])
                    except Exception: cant_d = 0.0

                raw_items.append({
                    "sku": sku_val,
                    "codigo_femaco": fem_val,
                    "nombre_producto": nombre_val,
                    "cantidad_pedida": cant_p,
                    "cantidad_despachada": cant_d,
                })

            if not raw_items:
                continue

            # 4. Consolidar tiendas/locales dentro de la misma OC por (SKU, VIN/Código Femaco)
            consolidated = {}
            for it in raw_items:
                key = (it["sku"].upper(), it["codigo_femaco"].upper())
                if key not in consolidated:
                    consolidated[key] = {
                        "sku": it["sku"],
                        "codigo_femaco": it["codigo_femaco"],
                        "nombre_producto": it["nombre_producto"],
                        "cantidad_pedida": 0.0,
                        "cantidad_despachada": 0.0,
                    }
                consolidated[key]["cantidad_pedida"] += it["cantidad_pedida"]
                consolidated[key]["cantidad_despachada"] += it["cantidad_despachada"]

            item_list = list(consolidated.values())

            # 5. Interpretar Estado OC y Etapa
            estado_raw_val = ""
            if col_estado_oc:
                ve = df_oc[col_estado_oc].dropna().astype(str).str.strip()
                if not ve.empty:
                    estado_raw_val = ve.iloc[0]

            sum_p_pre = sum(it["cantidad_pedida"] for it in item_list)
            sum_d_pre = sum(it["cantidad_despachada"] for it in item_list)

            oc_etapa, oc_estado = _interpret_estado_y_etapa(estado_raw_val, sum_p_pre, sum_d_pre, etapa_val)

            # Ajustes según la etapa final
            if oc_etapa == "PEDIDO":
                for it in item_list:
                    if it["cantidad_pedida"] == 0.0 and it["cantidad_despachada"] > 0.0:
                        it["cantidad_pedida"] = it["cantidad_despachada"]
                    it["cantidad_despachada"] = 0.0
                    it["diferencia"] = 0.0
                    it["estado_entrega"] = "PENDIENTE"
                    it["quiebre_detectado"] = False
                    it["desbalance_familiar"] = False
                    it["desbalance_detalle"] = ""
            elif oc_etapa == "ENTREGA":
                if not f_ent:
                    f_ent = f_ped or date.today()
                for it in item_list:
                    # Si no vino cantidad pedida pero sí despacho, asumir pedido = despacho
                    if it["cantidad_pedida"] == 0.0 and it["cantidad_despachada"] > 0.0:
                        it["cantidad_pedida"] = it["cantidad_despachada"]
                    dif = it["cantidad_despachada"] - it["cantidad_pedida"]
                    it["diferencia"] = dif

                    if it["cantidad_pedida"] > 0 and it["cantidad_despachada"] == 0:
                        it["estado_entrega"] = "NO_DESPACHADO"
                        it["quiebre_detectado"] = True
                    elif 0 < it["cantidad_despachada"] < it["cantidad_pedida"]:
                        it["estado_entrega"] = "DESPACHO_PARCIAL"
                        it["quiebre_detectado"] = False
                    elif it["cantidad_despachada"] == it["cantidad_pedida"]:
                        it["estado_entrega"] = "COMPLETO"
                        it["quiebre_detectado"] = False
                    elif it["cantidad_despachada"] > it["cantidad_pedida"]:
                        it["estado_entrega"] = "EXCEDENTE"
                        it["quiebre_detectado"] = False
                    else:
                        it["estado_entrega"] = "COMPLETO"
                        it["quiebre_detectado"] = False

                    it["desbalance_familiar"] = False
                    it["desbalance_detalle"] = ""

            # 6. Familias y Desbalance Familiar
            total_ped = sum(it["cantidad_pedida"] for it in item_list)
            total_desp = sum(it["cantidad_despachada"] for it in item_list)
            cumplimiento = (total_desp / total_ped * 100.0) if total_ped > 0 else (100.0 if total_desp > 0 else 0.0)

            quiebres_cnt = 0
            parciales_cnt = 0
            desbalance_cnt = 0

            for it in item_list:
                fem_u = it["codigo_femaco"].upper()
                sku_u = it["sku"].upper()
                fam_info = familias_map.get(fem_u) or familias_map.get(sku_u)
                if fam_info:
                    it["familia_id"] = fam_info["familia_id"]
                    it["nombre_familia"] = fam_info["nombre_familia"]
                else:
                    it["familia_id"] = None
                    it["nombre_familia"] = None

                if it.get("quiebre_detectado"):
                    quiebres_cnt += 1
                if it.get("estado_entrega") == "DESPACHO_PARCIAL":
                    parciales_cnt += 1

            if oc_etapa == "ENTREGA":
                fam_groups = {}
                for it in item_list:
                    if it["familia_id"]:
                        fam_groups.setdefault(it["familia_id"], []).append(it)

                for fid, f_items in fam_groups.items():
                    despachados = [it for it in f_items if it["cantidad_despachada"] > 0]
                    no_despachados = [it for it in f_items if it["cantidad_despachada"] == 0]
                    if despachados and no_despachados:
                        desbalance_cnt += len(f_items)
                        desp_names = ", ".join(f"{x['sku'] or x['codigo_femaco']} ({int(x['cantidad_despachada'])} uds)" for x in despachados)
                        nodesp_names = ", ".join(f"{x['sku'] or x['codigo_femaco']} (0 uds)" for x in no_despachados)
                        for it in f_items:
                            it["desbalance_familiar"] = True
                            if it["cantidad_despachada"] > 0:
                                it["desbalance_detalle"] = f"Se despachó este producto, pero sus hermanos no se despacharon: {nodesp_names}"
                            else:
                                it["desbalance_detalle"] = f"No se despachó (0 uds), mientras que otros miembros sí se despacharon: {desp_names}"

            # 7. Upsert en ordenes_compra_registro
            prev_oc = conn.execute(text("""
                SELECT id, etapa, fecha_pedido, total_pedido_uds
                FROM ordenes_compra_registro
                WHERE numero_oc = :num
                ORDER BY id DESC
                LIMIT 1
            """), {"num": oc_num}).fetchone()

            if prev_oc:
                oc_id = prev_oc.id
                conn.execute(text("""
                    UPDATE ordenes_compra_registro
                    SET cliente = :cli,
                        etapa = :etapa,
                        estado_oc = :estado_oc,
                        fecha_pedido = COALESCE(:fp, fecha_pedido),
                        fecha_entrega = COALESCE(:fe, fecha_entrega),
                        nombre_archivo = :fn,
                        total_items = :items,
                        total_pedido_uds = :tot_p,
                        total_despachado_uds = :tot_d,
                        cumplimiento_pct = :cump,
                        quiebres_count = :quiebres,
                        parciales_count = :parciales,
                        desbalance_familiar_count = :desbal,
                        usuario_carga = :user,
                        actualizado_en = NOW()
                    WHERE id = :oid
                """), {
                    "cli": cli,
                    "etapa": oc_etapa,
                    "estado_oc": oc_estado,
                    "fp": f_ped,
                    "fe": f_ent,
                    "fn": filename,
                    "items": len(item_list),
                    "tot_p": total_ped,
                    "tot_d": total_desp,
                    "cump": round(cumplimiento, 2),
                    "quiebres": quiebres_cnt,
                    "parciales": parciales_cnt,
                    "desbal": desbalance_cnt,
                    "user": usuario,
                    "oid": oc_id
                })
                # Reemplazar detalle previo
                conn.execute(text("DELETE FROM ordenes_compra_detalle WHERE oc_id = :oid"), {"oid": oc_id})
                action_type = "ACTUALIZADA"
            else:
                res_oc = conn.execute(text("""
                    INSERT INTO ordenes_compra_registro (
                        numero_oc, cliente, etapa, estado_oc, fecha_pedido, fecha_entrega,
                        nombre_archivo, total_items, total_pedido_uds, total_despachado_uds,
                        cumplimiento_pct, quiebres_count, parciales_count, desbalance_familiar_count,
                        usuario_carga, observaciones
                    ) VALUES (
                        :num, :cli, :etapa, :estado_oc, :fp, :fe,
                        :fn, :items, :tot_p, :tot_d,
                        :cump, :quiebres, :parciales, :desbal,
                        :user, :obs
                    ) RETURNING id
                """), {
                    "num": oc_num,
                    "cli": cli,
                    "etapa": oc_etapa,
                    "estado_oc": oc_estado,
                    "fp": f_ped,
                    "fe": f_ent,
                    "fn": filename,
                    "items": len(item_list),
                    "tot_p": total_ped,
                    "tot_d": total_desp,
                    "cump": round(cumplimiento, 2),
                    "quiebres": quiebres_cnt,
                    "parciales": parciales_cnt,
                    "desbal": desbalance_cnt,
                    "user": usuario,
                    "obs": f"Carga B2B ({oc_estado}) el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                })
                oc_id = res_oc.fetchone()[0]
                action_type = "NUEVA"

            # 8. Insertar detalle
            for it in item_list:
                conn.execute(text("""
                    INSERT INTO ordenes_compra_detalle (
                        oc_id, numero_oc, sku, codigo_femaco, nombre_producto,
                        cantidad_pedida, cantidad_despachada, diferencia, estado_entrega,
                        familia_id, nombre_familia, desbalance_familiar, desbalance_detalle,
                        quiebre_detectado, fecha_quiebre
                    ) VALUES (
                        :oid, :num, :sku, :fem, :nom,
                        :qp, :qd, :dif, :est,
                        :fid, :fnom, :desb, :desb_det,
                        :quieb, :fq
                    )
                """), {
                    "oid": oc_id,
                    "num": oc_num,
                    "sku": it["sku"],
                    "fem": it["codigo_femaco"],
                    "nom": it["nombre_producto"],
                    "qp": it["cantidad_pedida"],
                    "qd": it["cantidad_despachada"],
                    "dif": it["diferencia"],
                    "est": it["estado_entrega"],
                    "fid": it["familia_id"],
                    "fnom": it["nombre_familia"],
                    "desb": it["desbalance_familiar"],
                    "desb_det": it["desbalance_detalle"],
                    "quieb": it["quiebre_detectado"],
                    "fq": f_ent if it["quiebre_detectado"] else None
                })
                if it["sku"]: all_affected_skus.append(it["sku"])
                if it["codigo_femaco"]: all_affected_skus.append(it["codigo_femaco"])

            processed_results.append({
                "oc_id": oc_id,
                "numero_oc": oc_num,
                "etapa": oc_etapa,
                "estado_oc": oc_estado,
                "cliente": cli,
                "total_items": len(item_list),
                "total_pedido_uds": total_ped,
                "total_despachado_uds": total_desp,
                "cumplimiento_pct": round(cumplimiento, 2),
                "quiebres_count": quiebres_cnt,
                "parciales_count": parciales_cnt,
                "desbalance_familiar_count": desbalance_cnt,
                "tipo_accion": action_type
            })

        # Recalcular historial de quiebres y tiempos de recuperación
        if all_affected_skus:
            _recalcular_tiempos_recuperacion(conn, list(set(all_affected_skus)))

    if not processed_results:
        raise HTTPException(status_code=400, detail="No se pudo procesar ninguna orden de compra del archivo.")

    total_pedidos = sum(1 for r in processed_results if r["etapa"] == "PEDIDO")
    total_entregas = sum(1 for r in processed_results if r["etapa"] == "ENTREGA")
    total_nuevas = sum(1 for r in processed_results if r["tipo_accion"] == "NUEVA")
    total_actualizadas = sum(1 for r in processed_results if r["tipo_accion"] == "ACTUALIZADA")
    total_quiebres = sum(r["quiebres_count"] for r in processed_results)

    first_oc = processed_results[0]
    msg = f"Se procesaron {len(processed_results)} órdenes de compra ({total_entregas} entregas, {total_pedidos} pedidos pendientes). {total_actualizadas} actualizadas, {total_nuevas} nuevas."

    return {
        "ok": True,
        "total_ocs": len(processed_results),
        "total_pedidos": total_pedidos,
        "total_entregas": total_entregas,
        "total_nuevas": total_nuevas,
        "total_actualizadas": total_actualizadas,
        "total_quiebres_detectados": total_quiebres,
        "oc_id": first_oc["oc_id"] if len(processed_results) == 1 else None,
        "numero_oc": first_oc["numero_oc"] if len(processed_results) == 1 else None,
        "etapa": first_oc["etapa"] if len(processed_results) == 1 else "BATCH",
        "estado_oc": first_oc["estado_oc"] if len(processed_results) == 1 else "BATCH",
        "cumplimiento_pct": first_oc["cumplimiento_pct"] if len(processed_results) == 1 else None,
        "ocs": processed_results,
        "msg": msg
    }


def _clean_df_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convierte un DataFrame a una lista de diccionarios JSON-compliant (sin NaN, NaT o Decimales)."""
    if df.empty:
        return []
    import json
    return json.loads(df.to_json(orient="records", date_format="iso"))


@router.get("/")
def list_ordenes_compra():
    """Retorna listado general de OCs cargadas."""
    with engine.connect() as conn:
        df_ocs = pd.read_sql(text("""
            SELECT id, numero_oc, cliente, etapa, estado_oc,
                   fecha_pedido, fecha_entrega,
                   total_items, total_pedido_uds, total_despachado_uds,
                   cumplimiento_pct, quiebres_count, parciales_count,
                   desbalance_familiar_count, nombre_archivo,
                   fecha_carga, usuario_carga
            FROM ordenes_compra_registro
            ORDER BY COALESCE(fecha_entrega, fecha_pedido, fecha_carga::date) DESC, id DESC
        """), conn)

        return {"data": _clean_df_records(df_ocs)}


@router.get("/quiebres/historicos")
def list_quiebres_historicos():
    """
    Retorna la auditoría acumulada de todos los quiebres y el tiempo transcurrido
    hasta que se volvió a vender/despachar cada producto en OCs posteriores.
    Incluye estado del producto en catálogo (ACTIVO, BLOQUEADO, DESCONTINUADO).
    """
    with engine.connect() as conn:
        df_q = pd.read_sql(text("""
            SELECT d.id, d.numero_oc, d.sku, d.codigo_femaco, d.nombre_producto,
                   d.cantidad_pedida, d.cantidad_despachada,
                   d.nombre_familia, d.desbalance_familiar,
                   d.fecha_quiebre, d.oc_recuperacion, d.fecha_recuperacion,
                   d.dias_recuperacion_quiebre,
                   r.cliente, r.fecha_entrega AS fecha_oc,
                   COALESCE(
                       NULLIF(TRIM(p1.condicion), ''), NULLIF(TRIM(p1.estado), ''),
                       NULLIF(TRIM(p2.condicion), ''), NULLIF(TRIM(p2.estado), ''),
                       'ACTIVO'
                   ) AS estado_producto
            FROM ordenes_compra_detalle d
            JOIN ordenes_compra_registro r ON d.oc_id = r.id
            LEFT JOIN dim_productos p1 ON (d.sku IS NOT NULL AND TRIM(d.sku) != '' AND TRIM(d.sku) = TRIM(p1.sku))
            LEFT JOIN dim_productos p2 ON (d.codigo_femaco IS NOT NULL AND TRIM(d.codigo_femaco) != '' AND TRIM(d.codigo_femaco) = TRIM(p2.codigo_femaco) AND p1.sku IS NULL)
            WHERE d.quiebre_detectado = TRUE
            ORDER BY d.fecha_quiebre DESC NULLS LAST, d.id DESC
        """), conn)

        return {"data": _clean_df_records(df_q)}


@router.get("/{oc_id}")
def get_orden_compra_detail(oc_id: int):
    """Retorna detalle de una OC con su desglose de auditoría por producto y estado de catálogo."""
    with engine.connect() as conn:
        head = conn.execute(text("SELECT * FROM ordenes_compra_registro WHERE id = :id"), {"id": oc_id}).fetchone()
        if not head:
            raise HTTPException(status_code=404, detail="Orden de Compra no encontrada")

        header_dict = dict(head._mapping)
        for k, v in list(header_dict.items()):
            if isinstance(v, Decimal):
                header_dict[k] = float(v)
            elif isinstance(v, (datetime, date)):
                header_dict[k] = str(v)
            elif pd.isna(v) or v is None:
                header_dict[k] = None

        df_items = pd.read_sql(text("""
            SELECT d.id, d.numero_oc, d.sku, d.codigo_femaco, d.nombre_producto,
                   d.cantidad_pedida, d.cantidad_despachada, d.diferencia, d.estado_entrega,
                   d.familia_id, d.nombre_familia, d.desbalance_familiar, d.desbalance_detalle,
                   d.quiebre_detectado, d.fecha_quiebre, d.dias_recuperacion_quiebre,
                   d.oc_recuperacion, d.fecha_recuperacion,
                   COALESCE(
                       NULLIF(TRIM(p1.condicion), ''), NULLIF(TRIM(p1.estado), ''),
                       NULLIF(TRIM(p2.condicion), ''), NULLIF(TRIM(p2.estado), ''),
                       'ACTIVO'
                   ) AS estado_producto
            FROM ordenes_compra_detalle d
            LEFT JOIN dim_productos p1 ON (d.sku IS NOT NULL AND TRIM(d.sku) != '' AND TRIM(d.sku) = TRIM(p1.sku))
            LEFT JOIN dim_productos p2 ON (d.codigo_femaco IS NOT NULL AND TRIM(d.codigo_femaco) != '' AND TRIM(d.codigo_femaco) = TRIM(p2.codigo_femaco) AND p1.sku IS NULL)
            WHERE d.oc_id = :id
            ORDER BY 
                CASE d.estado_entrega 
                    WHEN 'NO_DESPACHADO' THEN 1 
                    WHEN 'DESPACHO_PARCIAL' THEN 2 
                    ELSE 3 
                END,
                d.desbalance_familiar DESC,
                d.id ASC
        """), conn, params={"id": oc_id})

        return {
            "header": header_dict,
            "items": _clean_df_records(df_items)
        }


@router.delete("/{oc_id}")
def delete_orden_compra(oc_id: int, authorization: str = Header(None)):
    """Elimina una orden de compra y su detalle."""
    token = _get_auth_header(authorization)
    decode_token(token)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ordenes_compra_registro WHERE id = :id"), {"id": oc_id})
    return {"ok": True, "msg": f"Orden de compra #{oc_id} eliminada correctamente"}


@router.get("/{oc_id}/export")
def export_orden_compra_excel(oc_id: int):
    """Descarga el reporte de auditoría de la OC en formato Excel."""
    with engine.connect() as conn:
        head = conn.execute(text("SELECT * FROM ordenes_compra_registro WHERE id = :id"), {"id": oc_id}).fetchone()
        if not head:
            raise HTTPException(status_code=404, detail="Orden no encontrada")

        df_items = pd.read_sql(text("""
            SELECT sku AS "SKU",
                   codigo_femaco AS "Cód. Interno",
                   nombre_producto AS "Producto",
                   nombre_familia AS "Familia / Hermanos",
                   cantidad_pedida AS "Cant. Pedida",
                   cantidad_despachada AS "Cant. Despachada",
                   diferencia AS "Diferencia",
                   estado_entrega AS "Estado Entrega",
                   CASE WHEN desbalance_familiar THEN 'SÍ' ELSE 'NO' END AS "Desbalance Familiar",
                   desbalance_detalle AS "Detalle Desbalance",
                   CASE WHEN quiebre_detectado THEN 'QUIEBRE' ELSE 'OK' END AS "Alerta Quiebre",
                   fecha_quiebre AS "Fecha Quiebre",
                   oc_recuperacion AS "OC Recuperación",
                   dias_recuperacion_quiebre AS "Días hasta Recuperación"
            FROM ordenes_compra_detalle
            WHERE oc_id = :id
            ORDER BY id ASC
        """), conn, params={"id": oc_id})

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_items.to_excel(writer, sheet_name=f"Auditoria_{head.numero_oc[:20]}", index=False)

        output.seek(0)
        filename = f"Auditoria_OC_{head.numero_oc}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
