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
    try:
        dt = pd.to_datetime(val, errors='coerce', dayfirst=True)
        if pd.notna(dt):
            return dt.date()
    except Exception:
        pass
    return None


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

    # Buscar todo el historial de entregas de estos SKUs ordenado por fecha de entrega / carga
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

    # Agrupar por SKU / Código
    history_by_sku = {}
    for r in rows:
        key = str(r["sku"] or r["codigo_femaco"]).strip().upper()
        history_by_sku.setdefault(key, []).append(dict(r))

    # Para cada SKU, emparejar quiebres con su siguiente re-despacho
    for key, items in history_by_sku.items():
        for i, item in enumerate(items):
            # Si hubo quiebre (pedido > 0 y despachado == 0)
            if float(item["cantidad_pedida"] or 0) > 0 and float(item["cantidad_despachada"] or 0) == 0:
                fecha_q = item["fecha_entrega"] or (item["fecha_carga"].date() if item["fecha_carga"] else None)
                recuperado_oc = None
                fecha_rec = None
                dias_rec = None

                # Buscar hacia adelante en items posteriores
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
    etapa: str = Form("ENTREGA"),
    numero_oc: Optional[str] = Form(None),
    cliente: Optional[str] = Form(""),
    fecha_pedido: Optional[str] = Form(None),
    fecha_entrega: Optional[str] = Form(None),
    authorization: str = Header(None)
):
    """
    Sube y procesa una Orden de Compra en etapa 'PEDIDO' (opcional) o 'ENTREGA' (despacho).
    Audita diferencias, detecta productos no despachados, parciales, desbalances familiares y quiebres.
    """
    token = _get_auth_header(authorization)
    user_payload = decode_token(token)
    usuario = user_payload.get("sub") or user_payload.get("username") or "sistema"

    etapa = etapa.strip().upper()
    if etapa not in ("PEDIDO", "ENTREGA"):
        raise HTTPException(status_code=400, detail="La etapa debe ser 'PEDIDO' o 'ENTREGA'")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # Leer Excel o CSV
    filename = file.filename or "archivo.xlsx"
    try:
        if filename.endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(content), sep=";", encoding="latin-1")
            except Exception:
                df = pd.read_csv(io.BytesIO(content), sep=",", encoding="utf-8")
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}")

    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas con datos")

    cols = list(df.columns)

    # Identificar columnas
    col_oc = _find_column(cols, [r"^(?:n[úu]mero[_\s]*oc|nro[_\s]*oc|orden[_\s]*compra|oc|pedido)$", r"n[úu]mero.*orden", r"nro.*pedido"])
    col_sku = _find_column(cols, [r"^(?:sku|c[oó]digo|c[oó]digo[_\s]*femaco|cod[_\s]*femaco|material|item)$"])
    col_femaco = _find_column(cols, [r"c[oó]d(?:igo)?[_\s]*femaco", r"c[oó]d(?:igo)?[_\s]*interno"])
    col_nombre = _find_column(cols, [r"^(?:nombre|nombre[_\s]*producto|descripci[oó]n|producto|modelo)$"])
    
    col_ped = _find_column(cols, [r"cant(?:idad)?[_\s]*(?:pedida|solicitada|comprada)", r"unidades[_\s]*(?:pedidas|compradas)", r"^pedido$", r"^solicitado$"])
    col_desp = _find_column(cols, [r"cant(?:idad)?[_\s]*(?:despachada|entregada|recibida)", r"unidades[_\s]*(?:despachadas|entregadas|recibidas)", r"^despacho$", r"^entregado$"])
    col_cliente = _find_column(cols, [r"cliente", r"raz[oó]n[_\s]*social", r"comprador"])
    col_fecha_p = _find_column(cols, [r"fecha[_\s]*pedido", r"fecha[_\s]*emisi[oó]n", r"fecha[_\s]*oc"])
    col_fecha_e = _find_column(cols, [r"fecha[_\s]*entrega", r"fecha[_\s]*despacho", r"fecha[_\s]*recepci[oó]n"])

    # Determinar número de OC
    oc_num = (numero_oc or "").strip()
    if not oc_num and col_oc:
        valid_vals = df[col_oc].dropna().astype(str).str.strip()
        if not valid_vals.empty:
            oc_num = valid_vals.iloc[0]
    if not oc_num:
        # Extraer de filename
        match_fn = re.search(r'(?:OC|ORDEN|PEDIDO)[_\s-]*([A-Za-z0-9_-]+)', filename, re.IGNORECASE)
        oc_num = match_fn.group(0) if match_fn else filename.rsplit('.', 1)[0]

    # Cliente
    cli = (cliente or "").strip()
    if not cli and col_cliente:
        vcli = df[col_cliente].dropna().astype(str).str.strip()
        if not vcli.empty:
            cli = vcli.iloc[0]

    # Fechas
    f_ped = _parse_date(fecha_pedido)
    if not f_ped and col_fecha_p:
        vfp = df[col_fecha_p].dropna()
        if not vfp.empty:
            f_ped = _parse_date(vfp.iloc[0])

    f_ent = _parse_date(fecha_entrega)
    if not f_ent and col_fecha_e:
        vfe = df[col_fecha_e].dropna()
        if not vfe.empty:
            f_ent = _parse_date(vfe.iloc[0])

    if etapa == 'ENTREGA' and not f_ent:
        f_ent = date.today()

    if not col_sku and not col_femaco:
        raise HTTPException(status_code=400, detail="No se encontró columna para SKU o Código Interno.")

    # Conexión DB
    with engine.begin() as conn:
        familias_map = _load_active_families(conn)

        # Cargar catálogo de planificacion_sop para rellenar descripciones si faltan
        sop_rows = conn.execute(text("SELECT sku, codigo_femaco, nombre_producto FROM planificacion_sop")).fetchall()
        sop_by_sku = {str(r.sku).strip().upper(): str(r.nombre_producto or '') for r in sop_rows if r.sku}
        sop_by_fem = {str(r.codigo_femaco).strip().upper(): str(r.nombre_producto or '') for r in sop_rows if r.codigo_femaco}
        sku_to_fem = {str(r.sku).strip().upper(): str(r.codigo_femaco or '') for r in sop_rows if r.sku}

        # Verificar si ya existe registro previo de esta OC
        prev_oc = conn.execute(text("""
            SELECT id, etapa, fecha_pedido, total_pedido_uds
            FROM ordenes_compra_registro
            WHERE numero_oc = :num
            ORDER BY id DESC
            LIMIT 1
        """), {"num": oc_num}).fetchone()

        prev_items_map = {}
        if prev_oc:
            rows_prev_items = conn.execute(text("""
                SELECT sku, codigo_femaco, cantidad_pedida
                FROM ordenes_compra_detalle
                WHERE oc_id = :oid
            """), {"oid": prev_oc.id}).fetchall()
            for pi in rows_prev_items:
                k_sku = str(pi.sku or '').strip().upper()
                k_fem = str(pi.codigo_femaco or '').strip().upper()
                if k_sku: prev_items_map[k_sku] = float(pi.cantidad_pedida or 0)
                if k_fem: prev_items_map[k_fem] = float(pi.cantidad_pedida or 0)
            if not f_ped and prev_oc.fecha_pedido:
                f_ped = prev_oc.fecha_pedido

        # Procesar filas
        raw_items = []
        for idx, row in df.iterrows():
            sku_val = str(row[col_sku]).strip() if col_sku and pd.notna(row.get(col_sku)) else ""
            fem_val = str(row[col_femaco]).strip() if col_femaco and pd.notna(row.get(col_femaco)) else ""
            if not sku_val and not fem_val:
                continue

            # Fallback de femaco <-> sku
            if sku_val and not fem_val and sku_val.upper() in sku_to_fem:
                fem_val = sku_to_fem[sku_val.upper()]

            # Nombre
            nombre_val = ""
            if col_nombre and pd.notna(row.get(col_nombre)):
                nombre_val = str(row[col_nombre]).strip()
            if not nombre_val:
                nombre_val = sop_by_sku.get(sku_val.upper()) or sop_by_fem.get(fem_val.upper()) or "Producto sin descripción"

            # Cantidades
            cant_p = 0.0
            cant_d = 0.0

            if col_ped and pd.notna(row.get(col_ped)):
                try: cant_p = float(row[col_ped])
                except Exception: cant_p = 0.0

            if col_desp and pd.notna(row.get(col_desp)):
                try: cant_d = float(row[col_desp])
                except Exception: cant_d = 0.0

            # Si estamos en PEDIDO y solo había 1 columna de cantidad
            if etapa == 'PEDIDO':
                if not col_ped and col_desp:
                    cant_p = cant_d
                    cant_d = 0.0
                elif not col_ped and not col_desp:
                    # Buscar alguna columna con números
                    for c in cols:
                        if c not in (col_sku, col_femaco, col_nombre, col_oc):
                            try:
                                val = float(row[c])
                                cant_p = val
                                break
                            except Exception:
                                pass
            elif etapa == 'ENTREGA':
                # Si no vino cantidad_pedida en el archivo de entrega pero teníamos registro de PEDIDO previo
                if cant_p == 0.0:
                    matched_prev_p = prev_items_map.get(sku_val.upper()) or prev_items_map.get(fem_val.upper())
                    if matched_prev_p is not None:
                        cant_p = matched_prev_p
                    elif col_desp is None and col_ped is not None:
                        # Si el archivo solo traía una columna llamada "cantidad", en entrega es el despacho
                        cant_d = cant_p
                        cant_p = 0.0

                # Si solo traía despacho y no pedido previo, asumir pedido = despacho (entrega 100% informada)
                if cant_p == 0.0 and cant_d > 0.0 and not prev_items_map:
                    cant_p = cant_d

            raw_items.append({
                "sku": sku_val,
                "codigo_femaco": fem_val,
                "nombre_producto": nombre_val,
                "cantidad_pedida": cant_p,
                "cantidad_despachada": cant_d,
            })

        if not raw_items:
            raise HTTPException(status_code=400, detail="No se encontraron líneas válidas de productos con cantidades.")

        # Consolidar líneas duplicadas dentro de la misma OC por SKU / Cód. Femaco
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

        # Enriquecer con familias y auditoría de despacho
        total_ped = sum(it["cantidad_pedida"] for it in item_list)
        total_desp = sum(it["cantidad_despachada"] for it in item_list)
        cumplimiento = (total_desp / total_ped * 100.0) if total_ped > 0 else (100.0 if total_desp > 0 else 0.0)

        quiebres_cnt = 0
        parciales_cnt = 0
        desbalance_cnt = 0

        # Mapear familia para cada item
        for it in item_list:
            fem_u = it["codigo_femaco"].upper()
            sku_u = it["sku"].upper()
            fam_info = familias_map.get(fem_u) or familias_map.get(sku_u)
            if fam_info:
                it["familia_id"] = fam_info["familia_id"]
                it["nombre_familia"] = fam_info["nombre_familia"]
                it["familia_miembros"] = fam_info["miembros"]
            else:
                it["familia_id"] = None
                it["nombre_familia"] = None
                it["familia_miembros"] = []

            # Estado de entrega
            dif = it["cantidad_despachada"] - it["cantidad_pedida"]
            it["diferencia"] = dif

            if etapa == 'ENTREGA':
                if it["cantidad_pedida"] > 0 and it["cantidad_despachada"] == 0:
                    it["estado_entrega"] = "NO_DESPACHADO"
                    it["quiebre_detectado"] = True
                    quiebres_cnt += 1
                elif 0 < it["cantidad_despachada"] < it["cantidad_pedida"]:
                    it["estado_entrega"] = "DESPACHO_PARCIAL"
                    it["quiebre_detectado"] = False
                    parciales_cnt += 1
                elif it["cantidad_despachada"] == it["cantidad_pedida"]:
                    it["estado_entrega"] = "COMPLETO"
                    it["quiebre_detectado"] = False
                elif it["cantidad_despachada"] > it["cantidad_pedida"]:
                    it["estado_entrega"] = "EXCEDENTE"
                    it["quiebre_detectado"] = False
                else:
                    it["estado_entrega"] = "COMPLETO"
                    it["quiebre_detectado"] = False
            else:
                it["estado_entrega"] = "PENDIENTE"
                it["quiebre_detectado"] = False

            it["desbalance_familiar"] = False
            it["desbalance_detalle"] = ""

        # Detección de Desbalance Familiar:
        # "si en las familias hay un producto que sí se despachó pero otros de esa misma familia no"
        if etapa == 'ENTREGA':
            fam_groups = {}
            for it in item_list:
                if it["familia_id"]:
                    fam_groups.setdefault(it["familia_id"], []).append(it)

            for fid, f_items in fam_groups.items():
                despachados = [it for it in f_items if it["cantidad_despachada"] > 0]
                no_despachados = [it for it in f_items if it["cantidad_despachada"] == 0]
                
                # Si al menos 1 se despachó y al menos 1 NO se despachó
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

        # Insertar registro principal
        res_oc = conn.execute(text("""
            INSERT INTO ordenes_compra_registro (
                numero_oc, cliente, etapa, fecha_pedido, fecha_entrega,
                nombre_archivo, total_items, total_pedido_uds, total_despachado_uds,
                cumplimiento_pct, quiebres_count, parciales_count, desbalance_familiar_count,
                usuario_carga, observaciones
            ) VALUES (
                :num, :cli, :etapa, :fp, :fe,
                :fn, :items, :tot_p, :tot_d,
                :cump, :quiebres, :parciales, :desbal,
                :user, :obs
            ) RETURNING id
        """), {
            "num": oc_num,
            "cli": cli,
            "etapa": etapa,
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
            "obs": f"Carga de {filename} el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        })
        oc_id = res_oc.fetchone()[0]

        # Insertar detalle
        skus_para_recalculo = []
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
            if it["sku"]: skus_para_recalculo.append(it["sku"])
            if it["codigo_femaco"]: skus_para_recalculo.append(it["codigo_femaco"])

        # Recalcular historial de quiebres y tiempos de recuperación
        if etapa == 'ENTREGA':
            _recalcular_tiempos_recuperacion(conn, skus_para_recalculo)

    return {
        "ok": True,
        "oc_id": oc_id,
        "numero_oc": oc_num,
        "etapa": etapa,
        "cliente": cli,
        "total_items": len(item_list),
        "total_pedido_uds": total_ped,
        "total_despachado_uds": total_desp,
        "cumplimiento_pct": round(cumplimiento, 2),
        "quiebres_count": quiebres_cnt,
        "parciales_count": parciales_cnt,
        "desbalance_familiar_count": desbalance_cnt,
        "msg": f"Orden de Compra {oc_num} procesada con éxito ({etapa})."
    }


@router.get("/")
def list_ordenes_compra():
    """Retorna listado general de OCs cargadas."""
    with engine.connect() as conn:
        df_ocs = pd.read_sql(text("""
            SELECT id, numero_oc, cliente, etapa,
                   fecha_pedido, fecha_entrega,
                   total_items, total_pedido_uds, total_despachado_uds,
                   cumplimiento_pct, quiebres_count, parciales_count,
                   desbalance_familiar_count, nombre_archivo,
                   fecha_carga, usuario_carga
            FROM ordenes_compra_registro
            ORDER BY COALESCE(fecha_entrega, fecha_pedido, fecha_carga::date) DESC, id DESC
        """), conn)
        
        # Formatear fechas para JSON
        for c in ["fecha_pedido", "fecha_entrega", "fecha_carga"]:
            if c in df_ocs.columns:
                df_ocs[c] = df_ocs[c].astype(str).replace({"None": None, "NaT": None, "nan": None})

        return {"data": df_ocs.to_dict(orient="records")}


@router.get("/{oc_id}")
def get_orden_compra_detail(oc_id: int):
    """Retorna detalle de una OC con su desglose de auditoría por producto."""
    with engine.connect() as conn:
        head = conn.execute(text("SELECT * FROM ordenes_compra_registro WHERE id = :id"), {"id": oc_id}).fetchone()
        if not head:
            raise HTTPException(status_code=404, detail="Orden de Compra no encontrada")

        header_dict = dict(head._mapping)
        for k in ["fecha_pedido", "fecha_entrega", "fecha_carga", "actualizado_en"]:
            if k in header_dict and header_dict[k]:
                header_dict[k] = str(header_dict[k])

        df_items = pd.read_sql(text("""
            SELECT id, numero_oc, sku, codigo_femaco, nombre_producto,
                   cantidad_pedida, cantidad_despachada, diferencia, estado_entrega,
                   familia_id, nombre_familia, desbalance_familiar, desbalance_detalle,
                   quiebre_detectado, fecha_quiebre, dias_recuperacion_quiebre,
                   oc_recuperacion, fecha_recuperacion
            FROM ordenes_compra_detalle
            WHERE oc_id = :id
            ORDER BY 
                CASE estado_entrega 
                    WHEN 'NO_DESPACHADO' THEN 1 
                    WHEN 'DESPACHO_PARCIAL' THEN 2 
                    ELSE 3 
                END,
                desbalance_familiar DESC,
                id ASC
        """), conn, params={"id": oc_id})

        for c in ["fecha_quiebre", "fecha_recuperacion"]:
            if c in df_items.columns:
                df_items[c] = df_items[c].astype(str).replace({"None": None, "NaT": None, "nan": None})

        return {
            "header": header_dict,
            "items": df_items.to_dict(orient="records")
        }


@router.delete("/{oc_id}")
def delete_orden_compra(oc_id: int, authorization: str = Header(None)):
    """Elimina una orden de compra y su detalle."""
    token = _get_auth_header(authorization)
    decode_token(token)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ordenes_compra_registro WHERE id = :id"), {"id": oc_id})
    return {"ok": True, "msg": f"Orden de compra #{oc_id} eliminada correctamente"}


@router.get("/quiebres/historicos")
def list_quiebres_historicos():
    """
    Retorna la auditoría acumulada de todos los quiebres y el tiempo transcurrido
    hasta que se volvió a vender/despachar cada producto en OCs posteriores.
    """
    with engine.connect() as conn:
        df_q = pd.read_sql(text("""
            SELECT d.id, d.numero_oc, d.sku, d.codigo_femaco, d.nombre_producto,
                   d.cantidad_pedida, d.cantidad_despachada,
                   d.nombre_familia, d.desbalance_familiar,
                   d.fecha_quiebre, d.oc_recuperacion, d.fecha_recuperacion,
                   d.dias_recuperacion_quiebre,
                   r.cliente, r.fecha_entrega AS fecha_oc
            FROM ordenes_compra_detalle d
            JOIN ordenes_compra_registro r ON d.oc_id = r.id
            WHERE d.quiebre_detectado = TRUE
            ORDER BY d.fecha_quiebre DESC NULLS LAST, d.id DESC
        """), conn)

        for c in ["fecha_quiebre", "fecha_recuperacion", "fecha_oc"]:
            if c in df_q.columns:
                df_q[c] = df_q[c].astype(str).replace({"None": None, "NaT": None, "nan": None})

        return {"data": df_q.to_dict(orient="records")}


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
