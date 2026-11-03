import io
import math
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal

from fastapi import APIRouter, File, UploadFile, HTTPException, Header, Body
import pandas as pd
from sqlalchemy import text

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()

def _require_admin(authorization: str):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol de administrador")
    return payload

def _safe(v, default=0):
    if v is None: return default
    try:
        if isinstance(v, float) and math.isnan(v): return default
        return int(round(float(v)))
    except Exception:
        return default

def _get_inventory_and_recipes(conn):
    """
    Devuelve:
    1. master: {sku: info} desde planificacion_sop, cruzado con recetas activas (familias de hermanos).
    2. materiales_dict: {sku: info} desde materiales_maquila (etiquetas, mangas, bolsas, etc.) con stock y costo.
    """
    # 1. Maestro SOP + Stock de productos
    df_sop = pd.read_sql(text("""
        SELECT sku, codigo_femaco, nombre_producto, stock_act, ump 
        FROM planificacion_sop
    """), conn)
    master = {}
    for _, r in df_sop.iterrows():
        sku_str = str(r["sku"] or "").strip()
        fem_str = str(r["codigo_femaco"] or "").strip()
        info = {
            "sku": sku_str,
            "codigo_femaco": fem_str,
            "nombre": r["nombre_producto"] or "Sin nombre",
            "stock_act": _safe(r["stock_act"]),
            "ump": r["ump"],
            "es_maquilable": False,
            "receta_id": None,
            "receta_info": {},
            "componentes": [],
            "materiales": [],
            "hermanos": []
        }
        if sku_str:
            master[sku_str] = info
        if fem_str and fem_str not in master:
            master[fem_str] = info

    # 2. Insumos y Materiales de Maquila
    df_mat = pd.read_sql(text("""
        SELECT sku, nombre, stock_actual, stock_minimo, costo_unitario, unidad_medida, categoria 
        FROM materiales_maquila 
        WHERE activo = TRUE
    """), conn)
    materiales_dict = {}
    for _, r in df_mat.iterrows():
        msku = str(r["sku"]).strip().upper()
        materiales_dict[msku] = {
            "sku": msku,
            "nombre": r["nombre"] or "Insumo",
            "stock_act": float(r["stock_actual"] or 0),
            "stock_minimo": float(r["stock_minimo"] or 0),
            "costo_unitario": float(r["costo_unitario"] or 0),
            "unidad_medida": r["unidad_medida"] or "UN",
            "categoria": r["categoria"] or "INSUMO"
        }

    # 3. Recetas Activas (Familias de Maquila)
    recetas = conn.execute(text("""
        SELECT id, sku_maquilable, descripcion, tiempo_base_1p_min, unidades_base_tiempo, 
               costo_hora, costo_maquila_estimado, producto_objetivo 
        FROM recetas_maquila 
        WHERE activa = TRUE
    """)).fetchall()

    recetas_by_id = {}
    for r in recetas:
        recetas_by_id[r.id] = {
            "id": r.id,
            "sku_maquilable": str(r.sku_maquilable or "").strip(),
            "descripcion": r.descripcion or "",
            "tiempo_base_1p_min": float(r.tiempo_base_1p_min or 45),
            "unidades_base_tiempo": int(r.unidades_base_tiempo or 100),
            "costo_hora": float(r.costo_hora or 0),
            "costo_maquila_estimado": float(r.costo_maquila_estimado or 0),
            "producto_objetivo": str(r.producto_objetivo or "").strip(),
            "componentes": []
        }

    # 4. Componentes de recetas
    if recetas_by_id:
        ids = list(recetas_by_id.keys())
        comps = conn.execute(text("""
            SELECT receta_id, sku_componente, cantidad_por_unidad, tipo_componente, 
                   nombre_componente, unidad_medida, costo_unitario, no_transformable, observacion
            FROM receta_maquila_componentes 
            WHERE receta_id = ANY(:ids)
        """), {"ids": ids}).fetchall()

        for c in comps:
            c_dict = {
                "sku": str(c.sku_componente or "").strip(),
                "qty": Decimal(str(c.cantidad_por_unidad or 1)),
                "tipo": str(c.tipo_componente or "PRODUCTO").strip().upper(),
                "nombre": str(c.nombre_componente or "").strip(),
                "um": str(c.unidad_medida or "UN").strip(),
                "costo_unitario": float(c.costo_unitario or 0),
                "no_transformable": bool(c.no_transformable),
                "observacion": str(c.observacion or "").strip()
            }
            recetas_by_id[c.receta_id]["componentes"].append(c_dict)

        # Vincular recetas a los SKUs en master
        for rid, rdata in recetas_by_id.items():
            mats = [c for c in rdata["componentes"] if c["tipo"] == "MATERIAL"]
            prods = [c for c in rdata["componentes"] if c["tipo"] != "MATERIAL"]

            # Todos los productos del grupo son potencialmente producibles
            all_product_skus = set()
            if rdata["sku_maquilable"]:
                all_product_skus.add(rdata["sku_maquilable"])
            if rdata["producto_objetivo"]:
                all_product_skus.add(rdata["producto_objetivo"])
            for p in prods:
                all_product_skus.add(p["sku"])

            for p_sku in all_product_skus:
                if p_sku in master:
                    master[p_sku]["es_maquilable"] = True
                    master[p_sku]["receta_id"] = rid
                    master[p_sku]["receta_info"] = rdata
                    master[p_sku]["materiales"] = mats
                    master[p_sku]["hermanos"] = [
                        p for p in prods if p["sku"] != p_sku and not p.get("no_transformable")
                    ]
                    master[p_sku]["componentes"] = rdata["componentes"]

    return master, materiales_dict


def procesar_df_oc(df: pd.DataFrame, master: dict, materiales_dict: dict):
    # Validaciones obligatorias de columnas
    required = ["Número OC", "SKU", "Modelo", "Unidades compradas", "Unidades recibidas"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Faltan columnas requeridas: {', '.join(missing)}")
        
    # Limpiar SKU
    df["SKU"] = df["SKU"].astype(str).str.strip()
    
    if df["SKU"].eq("").any() or df["SKU"].eq("nan").any():
        raise HTTPException(400, "El archivo contiene filas sin SKU válido.")
        
    for num_col in ["Unidades compradas", "Unidades recibidas"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
        if (df[num_col] < 0).any():
            raise HTTPException(400, f"Existen cantidades negativas en la columna '{num_col}'.")
            
    # Validar OC unica
    ocs = df["Número OC"].dropna().unique()
    if len(ocs) > 1:
        raise HTTPException(400, f"El archivo contiene más de un Número OC: {', '.join(map(str, ocs))}")
    if len(ocs) == 0:
        raise HTTPException(400, "No se detectó ningún Número OC.")
        
    oc_num = str(ocs[0])
    
    # Extraer meta de la primera fila util
    first_row = df.iloc[0]
    meta = {
        "numero_oc": oc_num,
        "estado_oc": str(first_row.get("Estado OC", "")),
        "tipo_orden": str(first_row.get("Tipo de orden", "")),
        "fecha_emision": str(first_row.get("Fecha de emisión", "")),
        "fecha_inicio_recepcion": str(first_row.get("Fecha inicio recepción", "")),
        "fecha_fin_recepcion": str(first_row.get("Fecha fin recepción", "")),
        "total_lineas": len(df)
    }
    
    # Validar que todos los SKUs existan
    invalid_skus = [s for s in df["SKU"].unique() if s not in master]
    if invalid_skus:
        raise HTTPException(400, f"Existen SKUs que no están en el maestro SOP: {', '.join(invalid_skus)}")

    # Agrupar por SKU
    grouped = df.groupby("SKU").agg({
        "Unidades compradas": "sum",
        "Unidades recibidas": "sum",
        "Modelo": "first",
        "Id de local": lambda x: list(x.dropna().unique()),
    }).reset_index()
    
    # Construir distribución
    distribucion = []
    for _, r in df.iterrows():
        distribucion.append({
            "sku": r["SKU"],
            "id_local": str(r.get("Id de local", "")),
            "local": str(r.get("Local", "")),
            "unidades_compradas": int(r["Unidades compradas"]),
            "unidades_recibidas": int(r["Unidades recibidas"]),
            "cantidad_empaque": int(_safe(r.get("Cantidad de empaque", 0)))
        })
        
    detalles = []
    comp_consolidados = {}
    total_costo_insumos = Decimal('0.0')
    total_costo_mo = Decimal('0.0')
    total_horas_1p = Decimal('0.0')
    
    for _, r in grouped.iterrows():
        sku = r["SKU"]
        m = master[sku]
        
        solicitada = int(r["Unidades compradas"])
        recibida = int(r["Unidades recibidas"])
        pendiente = max(0, solicitada - recibida)
        
        es_maq = m["es_maquilable"]
        rid = m["receta_id"]
        stock_term = m["stock_act"]
        
        a_maquilar = 0
        estado_analisis = ""
        
        if es_maq:
            a_maquilar = max(0, pendiente - stock_term)
            if pendiente == 0:
                estado_analisis = "Completado"
            elif a_maquilar == 0:
                estado_analisis = "Listo con stock terminado"
            else:
                estado_analisis = "Requiere maquila"
                
            if a_maquilar > 0:
                r_info = m.get("receta_info", {})
                t_base = float(r_info.get("tiempo_base_1p_min") or 45)
                u_base = float(r_info.get("unidades_base_tiempo") or 100)
                c_hora = Decimal(str(r_info.get("costo_hora") or 0))

                vel_uds_h = (u_base / t_base) * 60 if t_base > 0 else 100.0
                horas_item = Decimal(str(round(a_maquilar / vel_uds_h, 3)))
                costo_mo_item = horas_item * c_hora

                total_horas_1p += horas_item
                total_costo_mo += costo_mo_item

                # 1. Consolidar materiales/insumos (etiquetas, mangas, cajas)
                for mat in m.get("materiales", []):
                    c_sku = mat["sku"]
                    c_qty = mat["qty"] * a_maquilar
                    costo_u = Decimal(str(mat["costo_unitario"] or materiales_dict.get(c_sku, {}).get("costo_unitario", 0)))

                    if c_sku not in comp_consolidados:
                        comp_consolidados[c_sku] = {
                            "sku": c_sku,
                            "nombre": mat.get("nombre") or materiales_dict.get(c_sku, {}).get("nombre", "Insumo Maquila"),
                            "tipo": "MATERIAL",
                            "um": mat.get("um") or materiales_dict.get(c_sku, {}).get("unidad_medida", "UN"),
                            "requerido": Decimal('0.0'),
                            "costo_unitario": costo_u,
                            "utilizado_por": set()
                        }
                    comp_consolidados[c_sku]["requerido"] += c_qty
                    comp_consolidados[c_sku]["utilizado_por"].add(sku)
                    total_costo_insumos += (c_qty * costo_u)

                # 2. Consolidar requerimiento de productos hermanos (base a transformar)
                for hermano in m.get("hermanos", []):
                    h_sku = hermano["sku"]
                    h_qty = hermano["qty"] * a_maquilar
                    if h_sku not in comp_consolidados:
                        comp_consolidados[h_sku] = {
                            "sku": h_sku,
                            "nombre": master.get(h_sku, {}).get("nombre", hermano.get("nombre", "Producto Hermano")),
                            "tipo": "PRODUCTO",
                            "um": "UN",
                            "requerido": Decimal('0.0'),
                            "costo_unitario": Decimal(str(hermano.get("costo_unitario", 0))),
                            "utilizado_por": set()
                        }
                    comp_consolidados[h_sku]["requerido"] += h_qty
                    comp_consolidados[h_sku]["utilizado_por"].add(sku)
        else:
            if pendiente == 0:
                estado_analisis = "Completado"
            else:
                estado_analisis = "No maquilable"

        detalles.append({
            "sku": sku,
            "nombre_producto": r["Modelo"],
            "cantidad_solicitada": solicitada,
            "cantidad_recibida": recibida,
            "cantidad_pendiente": pendiente,
            "es_maquilable": es_maq,
            "receta_maquila_id": rid,
            "stock_producto_terminado": stock_term,
            "cantidad_a_maquilar": a_maquilar,
            "estado_analisis": estado_analisis,
            "locales": len(r["Id de local"])
        })
        
    # Evaluar componentes globales contra inventario
    comp_list = []
    faltantes_insumos = False
    faltantes_hermanos = False
    
    for c_sku, data in comp_consolidados.items():
        req = float(data["requerido"])
        is_material = (data["tipo"] == "MATERIAL")

        if is_material:
            mat_info = materiales_dict.get(c_sku, {})
            stock = float(mat_info.get("stock_act", 0))
            stock_min = float(mat_info.get("stock_minimo", 0))
            costo_u = float(data["costo_unitario"])
        else:
            stock = float(master.get(c_sku, {}).get("stock_act", 0))
            stock_min = 0.0
            costo_u = float(data["costo_unitario"])

        falt = max(0.0, req - stock)
        if falt > 0:
            if is_material:
                faltantes_insumos = True
            else:
                faltantes_hermanos = True
        
        comp_list.append({
            "sku": c_sku,
            "nombre": data["nombre"],
            "tipo": data["tipo"],
            "unidad_medida": data.get("um", "UN"),
            "requerido": req,
            "stock_actual": stock,
            "stock_minimo": stock_min,
            "costo_unitario": costo_u,
            "costo_total": round(req * costo_u, 2),
            "faltante": falt,
            "utilizado_por": list(data["utilizado_por"])
        })
        
    total_costo_total = total_costo_insumos + total_costo_mo

    estado_general = "Preparada"
    if any(d["cantidad_a_maquilar"] > 0 for d in detalles):
        if faltantes_insumos and faltantes_hermanos:
            estado_general = "Bloqueada por faltantes (Insumos y Hermanos)"
        elif faltantes_insumos:
            estado_general = "Bloqueada por falta de Insumos"
        elif faltantes_hermanos:
            estado_general = "Bloqueada por falta de Hermanos"
        else:
            estado_general = "En preparación"

    costos_resumen = {
        "costo_insumos_estimado": round(float(total_costo_insumos), 2),
        "costo_mo_estimado": round(float(total_costo_mo), 2),
        "costo_total_estimado": round(float(total_costo_total), 2),
        "horas_estimadas_1p": round(float(total_horas_1p), 2),
        "horas_estimadas_3p": round(float(total_horas_1p) / 2.7, 2) if total_horas_1p > 0 else 0.0,
        "horas_estimadas_6p": round(float(total_horas_1p) / 5.2, 2) if total_horas_1p > 0 else 0.0
    }

    return {
        "meta": meta,
        "detalles": detalles,
        "componentes": comp_list,
        "costos_resumen": costos_resumen,
        "estado_general": estado_general,
        "distribucion": distribucion
    }


@router.post("/importar")
async def importar_orden(
    file: UploadFile = File(...),
    authorization: str = Header(None)
):
    _require_admin(authorization)
    
    content = await file.read()
    hash_archivo = hashlib.sha256(content).hexdigest()
    
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo CSV. Verifique el formato.")
        
    if df.empty:
        raise HTTPException(400, "El archivo está vacío.")
        
    with engine.connect() as conn:
        master, materiales_dict = _get_inventory_and_recipes(conn)
        
        ocs = df.get("Número OC", pd.Series(dtype=str)).dropna().unique()
        if len(ocs) == 1:
            existe = conn.execute(
                text("SELECT 1 FROM ordenes_maquila WHERE numero_oc = :oc AND hash_archivo = :h"),
                {"oc": str(ocs[0]), "h": hash_archivo}
            ).fetchone()
            if existe:
                raise HTTPException(400, "Este archivo ya fue procesado para esta OC (Archivo duplicado).")

    res = procesar_df_oc(df, master, materiales_dict)
    res["meta"]["hash_archivo"] = hash_archivo
    res["meta"]["nombre_archivo"] = file.filename
    return res


@router.post("")
def guardar_orden(body: dict = Body(...), authorization: str = Header(None)):
    user = _require_admin(authorization).get("sub", "admin")
    
    meta = body.get("meta")
    detalles = body.get("detalles")
    dist = body.get("distribucion")
    costos = body.get("costos_resumen", {})
    
    if not meta or not detalles:
        raise HTTPException(400, "Faltan datos para guardar la orden.")
        
    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT id FROM ordenes_maquila WHERE numero_oc = :oc AND hash_archivo = :h"),
            {"oc": meta["numero_oc"], "h": meta["hash_archivo"]}
        ).fetchone()
        
        if existe:
            raise HTTPException(400, "La orden ya fue registrada.")
            
        def pdate(s):
            if not s or str(s).lower() == 'nan': return None
            try: return pd.to_datetime(s, dayfirst=True).date()
            except: return None
            
        r = conn.execute(
            text("""
                INSERT INTO ordenes_maquila 
                (numero_oc, nombre_archivo, estado_oc, tipo_orden, fecha_emision, 
                 fecha_inicio_recepcion, fecha_fin_recepcion, usuario_carga, 
                 estado_procesamiento, hash_archivo, activa,
                 costo_total_estimado, costo_insumos_estimado, costo_mo_estimado, horas_estimadas_1p)
                VALUES
                (:oc, :file, :est, :tipo, :fe, :fi, :ff, :user, :proc, :hash, TRUE,
                 :ctot, :cins, :cmo, :h1p)
                RETURNING id
            """),
            {
                "oc": meta["numero_oc"], "file": meta.get("nombre_archivo", ""),
                "est": meta.get("estado_oc"), "tipo": meta.get("tipo_orden"),
                "fe": pdate(meta.get("fecha_emision")), 
                "fi": pdate(meta.get("fecha_inicio_recepcion")),
                "ff": pdate(meta.get("fecha_fin_recepcion")),
                "user": user, "proc": body.get("estado_general", "Pendiente"),
                "hash": meta["hash_archivo"],
                "ctot": float(costos.get("costo_total_estimado") or 0),
                "cins": float(costos.get("costo_insumos_estimado") or 0),
                "cmo": float(costos.get("costo_mo_estimado") or 0),
                "h1p": float(costos.get("horas_estimadas_1p") or 0)
            }
        )
        oid = r.fetchone()[0]
        
        for d in detalles:
            conn.execute(
                text("""
                    INSERT INTO orden_maquila_detalle
                    (orden_id, sku, nombre_producto, cantidad_solicitada, cantidad_recibida,
                     cantidad_pendiente, es_maquilable, receta_maquila_id, stock_producto_terminado,
                     cantidad_a_maquilar, estado_analisis)
                    VALUES
                    (:oid, :sku, :nom, :sol, :rec, :pend, :es, :rid, :stock, :maq, :est)
                """),
                {
                    "oid": oid, "sku": d["sku"], "nom": d.get("nombre_producto", ""),
                    "sol": d["cantidad_solicitada"], "rec": d["cantidad_recibida"],
                    "pend": d["cantidad_pendiente"], "es": d["es_maquilable"],
                    "rid": d["receta_maquila_id"], "stock": d["stock_producto_terminado"],
                    "maq": d["cantidad_a_maquilar"], "est": d["estado_analisis"]
                }
            )
            
        if dist:
            for d in dist:
                conn.execute(
                    text("""
                        INSERT INTO orden_maquila_distribucion
                        (orden_id, sku, id_local, local, unidades_compradas, unidades_recibidas, cantidad_empaque)
                        VALUES
                        (:oid, :s, :il, :l, :uc, :ur, :ce)
                    """),
                    {
                        "oid": oid, "s": d["sku"], "il": d.get("id_local"), "l": d.get("local"),
                        "uc": d["unidades_compradas"], "ur": d["unidades_recibidas"], "ce": d["cantidad_empaque"]
                    }
                )
                
    return {"ok": True, "orden_id": oid}


@router.get("")
def listar_ordenes(authorization: str = Header(None)):
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, numero_oc, fecha_carga, estado_procesamiento, activa,
                   COALESCE(costo_total_estimado, 0) as costo_total_estimado,
                   COALESCE(horas_estimadas_1p, 0) as horas_estimadas_1p,
                   fecha_liquidacion, usuario_liquidacion,
                   (SELECT COUNT(*) FROM orden_maquila_detalle WHERE orden_id = o.id) as sku_count,
                   (SELECT COUNT(*) FROM orden_maquila_detalle WHERE orden_id = o.id AND es_maquilable=true) as maq_count
            FROM ordenes_maquila o
            ORDER BY id DESC
        """)).fetchall()
        
    out = []
    for r in res:
        out.append({
            "id": r.id,
            "numero_oc": r.numero_oc,
            "fecha_carga": str(r.fecha_carga)[:16] if r.fecha_carga else "",
            "estado_procesamiento": r.estado_procesamiento,
            "costo_total_estimado": float(r.costo_total_estimado or 0),
            "horas_estimadas_1p": float(r.horas_estimadas_1p or 0),
            "fecha_liquidacion": str(r.fecha_liquidacion)[:16] if r.fecha_liquidacion else None,
            "usuario_liquidacion": r.usuario_liquidacion,
            "activa": r.activa,
            "sku_count": r.sku_count,
            "maq_count": r.maq_count
        })
    return {"data": out}


@router.get("/{id}")
def obtener_orden(id: int, authorization: str = Header(None)):
    with engine.connect() as conn:
        oc = conn.execute(text("SELECT * FROM ordenes_maquila WHERE id = :id"), {"id": id}).fetchone()
        if not oc: raise HTTPException(404, "OC no encontrada")
        
        det = conn.execute(text("SELECT * FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id}).fetchall()
        dist = conn.execute(text("SELECT * FROM orden_maquila_distribucion WHERE orden_id = :id"), {"id": id}).fetchall()
        
        master, materiales_dict = _get_inventory_and_recipes(conn)
        
    det_list = []
    comp_consolidados = {}
    total_costo_insumos = Decimal('0.0')
    total_costo_mo = Decimal('0.0')
    total_horas_1p = Decimal('0.0')
    
    for d in det:
        sku = d.sku
        m = master.get(sku, {})
        sol = d.cantidad_solicitada
        rec = d.cantidad_recibida
        pend = max(0, sol - rec)
        
        es_maq = m.get("es_maquilable", False)
        rid = m.get("receta_id")
        stock_term = m.get("stock_act", 0)
        
        a_maquilar = 0
        estado_analisis = d.estado_analisis
        if es_maq:
            a_maquilar = max(0, pend - stock_term)
            if pend == 0:
                estado_analisis = "Completado"
            elif a_maquilar == 0:
                estado_analisis = "Listo con stock terminado"
            else:
                estado_analisis = "Requiere maquila"

            if a_maquilar > 0:
                r_info = m.get("receta_info", {})
                t_base = float(r_info.get("tiempo_base_1p_min") or 45)
                u_base = float(r_info.get("unidades_base_tiempo") or 100)
                c_hora = Decimal(str(r_info.get("costo_hora") or 0))

                vel_uds_h = (u_base / t_base) * 60 if t_base > 0 else 100.0
                horas_item = Decimal(str(round(a_maquilar / vel_uds_h, 3)))
                costo_mo_item = horas_item * c_hora

                total_horas_1p += horas_item
                total_costo_mo += costo_mo_item

                # Insumos
                for mat in m.get("materiales", []):
                    c_sku = mat["sku"]
                    c_qty = mat["qty"] * a_maquilar
                    costo_u = Decimal(str(mat["costo_unitario"] or materiales_dict.get(c_sku, {}).get("costo_unitario", 0)))
                    if c_sku not in comp_consolidados:
                        comp_consolidados[c_sku] = {
                            "sku": c_sku,
                            "nombre": mat.get("nombre") or materiales_dict.get(c_sku, {}).get("nombre", "Insumo Maquila"),
                            "tipo": "MATERIAL",
                            "um": mat.get("um") or materiales_dict.get(c_sku, {}).get("unidad_medida", "UN"),
                            "requerido": Decimal('0.0'),
                            "costo_unitario": costo_u,
                            "utilizado_por": set()
                        }
                    comp_consolidados[c_sku]["requerido"] += c_qty
                    comp_consolidados[c_sku]["utilizado_por"].add(sku)
                    total_costo_insumos += (c_qty * costo_u)

                # Hermanos
                for hermano in m.get("hermanos", []):
                    h_sku = hermano["sku"]
                    h_qty = hermano["qty"] * a_maquilar
                    if h_sku not in comp_consolidados:
                        comp_consolidados[h_sku] = {
                            "sku": h_sku,
                            "nombre": master.get(h_sku, {}).get("nombre", hermano.get("nombre", "Producto Hermano")),
                            "tipo": "PRODUCTO",
                            "um": "UN",
                            "requerido": Decimal('0.0'),
                            "costo_unitario": Decimal(str(hermano.get("costo_unitario", 0))),
                            "utilizado_por": set()
                        }
                    comp_consolidados[h_sku]["requerido"] += h_qty
                    comp_consolidados[h_sku]["utilizado_por"].add(sku)
        else:
            if pend == 0:
                estado_analisis = "Completado"
            else:
                estado_analisis = "No maquilable"
                    
        det_list.append({
            "sku": sku,
            "nombre_producto": d.nombre_producto,
            "cantidad_solicitada": sol,
            "cantidad_recibida": rec,
            "cantidad_pendiente": pend,
            "es_maquilable": es_maq,
            "receta_maquila_id": rid,
            "stock_producto_terminado": stock_term,
            "cantidad_a_maquilar": a_maquilar,
            "estado_analisis": estado_analisis,
            "hermanos_disponibles": m.get("hermanos", [])
        })
        
    comp_list = []
    faltantes_insumos = False
    faltantes_hermanos = False
    
    for c_sku, data in comp_consolidados.items():
        req = float(data["requerido"])
        is_material = (data["tipo"] == "MATERIAL")

        if is_material:
            mat_info = materiales_dict.get(c_sku, {})
            stock = float(mat_info.get("stock_act", 0))
            stock_min = float(mat_info.get("stock_minimo", 0))
            costo_u = float(data["costo_unitario"])
        else:
            stock = float(master.get(c_sku, {}).get("stock_act", 0))
            stock_min = 0.0
            costo_u = float(data["costo_unitario"])

        falt = max(0.0, req - stock)
        if falt > 0:
            if is_material:
                faltantes_insumos = True
            else:
                faltantes_hermanos = True
        
        comp_list.append({
            "sku": c_sku,
            "nombre": data["nombre"],
            "tipo": data["tipo"],
            "unidad_medida": data.get("um", "UN"),
            "requerido": req,
            "stock_actual": stock,
            "stock_minimo": stock_min,
            "costo_unitario": costo_u,
            "costo_total": round(req * costo_u, 2),
            "faltante": falt,
            "utilizado_por": list(data["utilizado_por"])
        })
        
    total_costo_total = total_costo_insumos + total_costo_mo

    estado_general = "Preparada"
    if any(d["cantidad_a_maquilar"] > 0 for d in det_list):
        if faltantes_insumos and faltantes_hermanos:
            estado_general = "Bloqueada por faltantes (Insumos y Hermanos)"
        elif faltantes_insumos:
            estado_general = "Bloqueada por falta de Insumos"
        elif faltantes_hermanos:
            estado_general = "Bloqueada por falta de Hermanos"
        else:
            estado_general = "En preparación"

    meta_dict = dict(oc._mapping)
    # Si ya estaba liquidada, mantener ese estado histórico
    if meta_dict.get("estado_procesamiento") == "Liquidada":
        meta_dict["estado_procesamiento"] = "Liquidada"
    else:
        meta_dict["estado_procesamiento"] = estado_general

    costos_resumen = {
        "costo_insumos_estimado": round(float(total_costo_insumos), 2),
        "costo_mo_estimado": round(float(total_costo_mo), 2),
        "costo_total_estimado": round(float(total_costo_total), 2),
        "horas_estimadas_1p": round(float(total_horas_1p), 2),
        "horas_estimadas_3p": round(float(total_horas_1p) / 2.7, 2) if total_horas_1p > 0 else 0.0,
        "horas_estimadas_6p": round(float(total_horas_1p) / 5.2, 2) if total_horas_1p > 0 else 0.0
    }

    return {
        "meta": meta_dict,
        "detalles": det_list,
        "componentes": comp_list,
        "costos_resumen": costos_resumen,
        "distribucion": [dict(di._mapping) for di in dist]
    }


@router.patch("/{id}/estado")
def actualizar_estado_orden(id: int, body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    est = body.get("estado_procesamiento")
    obs = body.get("observaciones")
    activa = body.get("activa")
    
    updates = []
    params = {"id": id}
    
    if est is not None:
        updates.append("estado_procesamiento = :est")
        params["est"] = est
    if obs is not None:
        updates.append("observaciones = :obs")
        params["obs"] = obs
    if activa is not None:
        updates.append("activa = :act")
        params["act"] = activa
        
    if not updates:
        raise HTTPException(400, "Nada que actualizar")
        
    with engine.begin() as conn:
        res = conn.execute(text(f"UPDATE ordenes_maquila SET {', '.join(updates)} WHERE id = :id RETURNING id"), params)
        if not res.fetchone():
            raise HTTPException(404, "OC no encontrada")
            
    return {"ok": True}


@router.post("/{id}/recalcular")
def recalcular_orden(id: int, authorization: str = Header(None)):
    _require_admin(authorization)
    with engine.begin() as conn:
        oc = conn.execute(text("SELECT * FROM ordenes_maquila WHERE id = :id"), {"id": id}).fetchone()
        if not oc: raise HTTPException(404, "OC no encontrada")
        
        dist = conn.execute(text("SELECT * FROM orden_maquila_distribucion WHERE orden_id = :id"), {"id": id}).fetchall()
        if not dist: raise HTTPException(400, "No hay distribución guardada para recalcular")
        
        data = []
        for d in dist:
            data.append({
                "Número OC": oc.numero_oc,
                "Estado OC": oc.estado_oc,
                "Tipo de orden": oc.tipo_orden,
                "Fecha de emisión": oc.fecha_emision,
                "Fecha inicio recepción": oc.fecha_inicio_recepcion,
                "Fecha fin recepción": oc.fecha_fin_recepcion,
                "SKU": d.sku,
                "Id de local": d.id_local,
                "Local": d.local,
                "Unidades compradas": d.unidades_compradas,
                "Unidades recibidas": d.unidades_recibidas,
                "Cantidad de empaque": d.cantidad_empaque
            })
            
        df = pd.DataFrame(data)
        
        det = conn.execute(text("SELECT sku, nombre_producto FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id}).fetchall()
        nombres = {d.sku: d.nombre_producto for d in det}
        df["Modelo"] = df["SKU"].map(lambda x: nombres.get(x, ""))
        
        master, materiales_dict = _get_inventory_and_recipes(conn)
        res = procesar_df_oc(df, master, materiales_dict)
        costos = res.get("costos_resumen", {})
        
        conn.execute(text("DELETE FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id})
        
        for d in res["detalles"]:
            conn.execute(
                text("""
                    INSERT INTO orden_maquila_detalle
                    (orden_id, sku, nombre_producto, cantidad_solicitada, cantidad_recibida,
                     cantidad_pendiente, es_maquilable, receta_maquila_id, stock_producto_terminado,
                     cantidad_a_maquilar, estado_analisis)
                    VALUES
                    (:oid, :sku, :nom, :sol, :rec, :pend, :es, :rid, :stock, :maq, :est)
                """),
                {
                    "oid": id, "sku": d["sku"], "nom": d.get("nombre_producto", ""),
                    "sol": d["cantidad_solicitada"], "rec": d["cantidad_recibida"],
                    "pend": d["cantidad_pendiente"], "es": d["es_maquilable"],
                    "rid": d["receta_maquila_id"], "stock": d["stock_producto_terminado"],
                    "maq": d["cantidad_a_maquilar"], "est": d["estado_analisis"]
                }
            )
            
        conn.execute(text("""
            UPDATE ordenes_maquila 
            SET estado_procesamiento = :est,
                costo_total_estimado = :ctot,
                costo_insumos_estimado = :cins,
                costo_mo_estimado = :cmo,
                horas_estimadas_1p = :h1p
            WHERE id = :id
        """), {
            "est": res["estado_general"],
            "ctot": float(costos.get("costo_total_estimado") or 0),
            "cins": float(costos.get("costo_insumos_estimado") or 0),
            "cmo": float(costos.get("costo_mo_estimado") or 0),
            "h1p": float(costos.get("horas_estimadas_1p") or 0),
            "id": id
        })
        
    return {"ok": True}


@router.post("/{id}/liquidar")
def liquidar_orden(id: int, body: dict = Body(...), authorization: str = Header(None)):
    """
    Ejecuta la liquidación de la orden de maquila:
    1. Descuenta los materiales utilizados de 'materiales_maquila'.
    2. Descuenta los productos hermanos utilizados de 'planificacion_sop'.
    3. Suma los productos terminados obtenidos a 'planificacion_sop'.
    4. Marca la orden como 'Liquidada' y registra la auditoría (kardex) en 'maquila_liquidaciones_historial'.
    """
    user_payload = _require_admin(authorization)
    user = user_payload.get("sub", "admin")
    
    observaciones = str(body.get("observaciones") or "").strip()
    # Mapeo manual opcional: { sku_producido: sku_origen_usado }
    hermano_seleccionado = body.get("hermano_seleccionado") or {}

    with engine.begin() as conn:
        oc = conn.execute(text("SELECT * FROM ordenes_maquila WHERE id = :id"), {"id": id}).fetchone()
        if not oc:
            raise HTTPException(404, "Orden de maquila no encontrada")
        if oc.estado_procesamiento == "Liquidada":
            raise HTTPException(400, "Esta orden de maquila ya fue liquidada previamente")

        det = conn.execute(text("SELECT * FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id}).fetchall()
        if not det:
            raise HTTPException(400, "La orden no tiene ítems de detalle")

        master, materiales_dict = _get_inventory_and_recipes(conn)

        items_liquidados = []
        total_costo_liquidado = Decimal('0.0')

        for d in det:
            sku_prod = d.sku
            cant_a_maq = d.cantidad_a_maquilar
            if cant_a_maq <= 0:
                continue

            m = master.get(sku_prod, {})
            if not m.get("es_maquilable"):
                continue

            # Determinar hermano de origen a descontar
            hermanos_disp = m.get("hermanos", [])
            sku_orig = hermano_seleccionado.get(sku_prod)
            if not sku_orig and hermanos_disp:
                # Elegir el primer hermano con stock suficiente, o el primero disponible
                hermano_con_stock = next((h for h in hermanos_disp if master.get(h["sku"], {}).get("stock_act", 0) >= cant_a_maq), hermanos_disp[0])
                sku_orig = hermano_con_stock["sku"]

            cant_orig_usada = Decimal(str(cant_a_maq))

            # Descontar hermano origen en planificacion_sop
            if sku_orig:
                conn.execute(text("""
                    UPDATE planificacion_sop
                    SET stock_act = GREATEST(0, stock_act - :qty)
                    WHERE sku = :sku OR codigo_femaco = :sku
                """), {"qty": float(cant_orig_usada), "sku": sku_orig})

            # Sumar producto terminado en planificacion_sop
            conn.execute(text("""
                UPDATE planificacion_sop
                SET stock_act = stock_act + :qty
                WHERE sku = :sku OR codigo_femaco = :sku
            """), {"qty": float(cant_a_maq), "sku": sku_prod})

            # Descontar insumos en materiales_maquila
            insumos_usados = []
            for mat in m.get("materiales", []):
                mat_sku = mat["sku"]
                mat_qty = mat["qty"] * cant_a_maq
                costo_u = Decimal(str(mat["costo_unitario"] or materiales_dict.get(mat_sku, {}).get("costo_unitario", 0)))
                costo_tot = mat_qty * costo_u
                total_costo_liquidado += costo_tot

                conn.execute(text("""
                    UPDATE materiales_maquila
                    SET stock_actual = GREATEST(0, stock_actual - :qty),
                        fecha_actualizacion = NOW()
                    WHERE UPPER(sku) = :sku
                """), {"qty": float(mat_qty), "sku": mat_sku.upper()})

                insumos_usados.append({
                    "sku": mat_sku,
                    "cantidad": float(mat_qty),
                    "costo_unitario": float(costo_u),
                    "costo_total": float(costo_tot)
                })

            # Registrar en historial de liquidaciones
            conn.execute(text("""
                INSERT INTO maquila_liquidaciones_historial (
                    orden_id, numero_oc, sku_producido, cantidad_producida, 
                    sku_origen, cantidad_origen_usada, detalles_insumos_json, 
                    costo_total_liquidado, observaciones, usuario
                ) VALUES (
                    :oid, :oc, :sprod, :cprod, :sorig, :corig, :ijson, :ctot, :obs, :user
                )
            """), {
                "oid": id,
                "oc": oc.numero_oc,
                "sprod": sku_prod,
                "cprod": cant_a_maq,
                "sorig": sku_orig or "N/A",
                "corig": float(cant_orig_usada),
                "ijson": json.dumps(insumos_usados),
                "ctot": float(total_costo_liquidado),
                "obs": observaciones,
                "user": user
            })

            items_liquidados.append({
                "sku_producido": sku_prod,
                "cantidad_producida": cant_a_maq,
                "sku_origen": sku_orig,
                "cantidad_origen": float(cant_orig_usada),
                "insumos": insumos_usados
            })

        # Actualizar estado de la orden a 'Liquidada'
        conn.execute(text("""
            UPDATE ordenes_maquila
            SET estado_procesamiento = 'Liquidada',
                fecha_liquidacion = NOW(),
                usuario_liquidacion = :user,
                observaciones = CASE 
                    WHEN observaciones IS NULL OR observaciones = '' THEN :obs 
                    ELSE observaciones || ' | Liquidado: ' || :obs 
                END
            WHERE id = :id
        """), {
            "id": id,
            "user": user,
            "obs": observaciones or "Maquila completada e inventarios actualizados"
        })

    return {
        "ok": True,
        "mensaje": f"Orden {oc.numero_oc} liquidada con éxito. Inventarios de insumos y productos actualizados.",
        "items_liquidados": items_liquidados,
        "costo_insumos_liquidado": float(total_costo_liquidado)
    }


@router.get("/{id}/ot")
def generar_ot_orden(id: int, authorization: str = Header(None)):
    """
    Genera el detalle estructurado de la Orden de Trabajo (OT) / Hoja de Ruta para Bodega y Maquila:
    - Datos generales de la OC y lote a producir.
    - Picking List de Bodega (Insumos y Productos Hermanos a despachar).
    - Dotación y Tiempos de fabricación calculados.
    - Plantilla para firmas de recepción, control de mermas y entrega a bodega de producto terminado.
    """
    with engine.connect() as conn:
        oc = conn.execute(text("SELECT * FROM ordenes_maquila WHERE id = :id"), {"id": id}).fetchone()
        if not oc:
            raise HTTPException(404, "OC no encontrada")
            
        det = conn.execute(text("SELECT * FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id}).fetchall()
        master, materiales_dict = _get_inventory_and_recipes(conn)

    picking_insumos = []
    picking_hermanos = []
    productos_a_producir = []
    total_unidades = 0
    total_horas = Decimal('0.0')

    for d in det:
        if d.cantidad_a_maquilar <= 0:
            continue
        total_unidades += d.cantidad_a_maquilar
        sku = d.sku
        m = master.get(sku, {})
        r_info = m.get("receta_info", {})

        t_base = float(r_info.get("tiempo_base_1p_min") or 45)
        u_base = float(r_info.get("unidades_base_tiempo") or 100)
        vel = (u_base / t_base) * 60 if t_base > 0 else 100.0
        horas_item = Decimal(str(round(d.cantidad_a_maquilar / vel, 2)))
        total_horas += horas_item

        productos_a_producir.append({
            "sku": sku,
            "nombre": d.nombre_producto,
            "cantidad_a_producir": d.cantidad_a_maquilar,
            "receta_id": d.receta_maquila_id,
            "velocidad_uds_h": round(vel, 1),
            "horas_estimadas_1p": float(horas_item)
        })

        for mat in m.get("materiales", []):
            msku = mat["sku"]
            mqty = float(mat["qty"] * d.cantidad_a_maquilar)
            stock_act = materiales_dict.get(msku, {}).get("stock_act", 0)
            picking_insumos.append({
                "sku": msku,
                "nombre": mat.get("nombre") or materiales_dict.get(msku, {}).get("nombre", "Insumo"),
                "categoria": materiales_dict.get(msku, {}).get("categoria", "INSUMO"),
                "unidad_medida": mat.get("um") or "UN",
                "cantidad_despachar": mqty,
                "stock_bodega": stock_act,
                "para_producto": sku
            })

        for hermano in m.get("hermanos", []):
            hsku = hermano["sku"]
            hqty = float(hermano["qty"] * d.cantidad_a_maquilar)
            stock_act = master.get(hsku, {}).get("stock_act", 0)
            picking_hermanos.append({
                "sku": hsku,
                "nombre": master.get(hsku, {}).get("nombre", hermano.get("nombre", "Hermano")),
                "unidad_medida": "UN",
                "cantidad_despachar": hqty,
                "stock_bodega": stock_act,
                "para_producto": sku
            })

    return {
        "ok": True,
        "ot_numero": f"OT-MAQ-{oc.id:05d}",
        "fecha_emision": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "oc": {
            "id": oc.id,
            "numero_oc": oc.numero_oc,
            "tipo_orden": oc.tipo_orden,
            "estado_oc": oc.estado_oc,
            "fecha_emision": str(oc.fecha_emision or ""),
            "fecha_fin_recepcion": str(oc.fecha_fin_recepcion or ""),
            "estado_procesamiento": oc.estado_procesamiento
        },
        "resumen_produccion": {
            "total_unidades": total_unidades,
            "total_horas_1p": float(total_horas),
            "total_horas_3p": round(float(total_horas) / 2.7, 1) if total_horas > 0 else 0,
            "total_horas_6p": round(float(total_horas) / 5.2, 1) if total_horas > 0 else 0,
            "costo_total_estimado": float(oc.costo_total_estimado or 0),
            "costo_mo_estimado": float(oc.costo_mo_estimado or 0),
            "costo_insumos_estimado": float(oc.costo_insumos_estimado or 0)
        },
        "productos_a_producir": productos_a_producir,
        "picking_insumos": picking_insumos,
        "picking_hermanos": picking_hermanos
    }
