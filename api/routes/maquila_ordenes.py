import io
import math
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
    Devuelve un diccionario {sku: info} desde planificacion_sop, 
    cruzado con recetas activas y sus componentes.
    """
    # 1. Maestro + Stock
    df_sop = pd.read_sql(text("SELECT sku, nombre_producto, stock_act, ump FROM planificacion_sop"), conn)
    master = {}
    for _, r in df_sop.iterrows():
        master[str(r["sku"])] = {
            "nombre": r["nombre_producto"],
            "stock_act": _safe(r["stock_act"]),
            "ump": r["ump"],
            "es_maquilable": False,
            "receta_id": None,
            "componentes": []
        }
    
    # 2. Recetas Activas
    recetas = conn.execute(text("SELECT id, sku_maquilable FROM recetas_maquila WHERE activa = TRUE")).fetchall()
    recetas_map = {str(r.sku_maquilable): r.id for r in recetas}
    
    # 3. Componentes
    if recetas_map:
        ids = list(recetas_map.values())
        comps = conn.execute(text("SELECT receta_id, sku_componente, cantidad_por_unidad FROM receta_maquila_componentes WHERE receta_id = ANY(:ids)"), {"ids": ids}).fetchall()
        
        comps_by_rec = {}
        for c in comps:
            comps_by_rec.setdefault(c.receta_id, []).append({
                "sku": str(c.sku_componente),
                "qty": Decimal(str(c.cantidad_por_unidad))
            })
            
        for sku, rid in recetas_map.items():
            if sku in master:
                master[sku]["es_maquilable"] = True
                master[sku]["receta_id"] = rid
                master[sku]["componentes"] = comps_by_rec.get(rid, [])
                
    return master

def procesar_df_oc(df: pd.DataFrame, master: dict):
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
        raise HTTPException(400, f"Existen SKUs que no están en el maestro: {', '.join(invalid_skus)}")

    # Agrupar por SKU
    grouped = df.groupby("SKU").agg({
        "Unidades compradas": "sum",
        "Unidades recibidas": "sum",
        "Modelo": "first",
        "Id de local": lambda x: list(x.dropna().unique()),
    }).reset_index()
    
    # Construir distribución (conservar original)
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
        
    # Calcular cantidades
    detalles = []
    comp_consolidados = {}
    
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
                
            # Agregar componentes
            if a_maquilar > 0:
                for comp in m["componentes"]:
                    c_sku = comp["sku"]
                    c_qty = comp["qty"] * a_maquilar
                    
                    if c_sku not in comp_consolidados:
                        comp_consolidados[c_sku] = {
                            "sku": c_sku,
                            "nombre": master.get(c_sku, {}).get("nombre", "Desconocido"),
                            "requerido": Decimal('0.0'),
                            "utilizado_por": set()
                        }
                    comp_consolidados[c_sku]["requerido"] += c_qty
                    comp_consolidados[c_sku]["utilizado_por"].add(sku)
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
    faltantes = False
    
    for c_sku, data in comp_consolidados.items():
        req = float(data["requerido"])
        stock = master.get(c_sku, {}).get("stock_act", 0)
        falt = max(0, req - stock)
        if falt > 0: faltantes = True
        
        comp_list.append({
            "sku": c_sku,
            "nombre": data["nombre"],
            "requerido": req,
            "stock_actual": stock,
            "faltante": falt,
            "utilizado_por": list(data["utilizado_por"])
        })
        
    estado_general = "Preparada"
    if any(d["cantidad_a_maquilar"] > 0 for d in detalles):
        if faltantes:
            estado_general = "Bloqueada por faltantes"
        else:
            estado_general = "En preparación"

    return {
        "meta": meta,
        "detalles": detalles,
        "componentes": comp_list,
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
    except Exception as e:
        raise HTTPException(400, "No se pudo leer el archivo CSV. Verifique el formato.")
        
    if df.empty:
        raise HTTPException(400, "El archivo está vacío.")
        
    with engine.connect() as conn:
        master = _get_inventory_and_recipes(conn)
        
        # Verificar si ya existe este hash para esta OC
        ocs = df.get("Número OC", pd.Series(dtype=str)).dropna().unique()
        if len(ocs) == 1:
            existe = conn.execute(
                text("SELECT 1 FROM ordenes_maquila WHERE numero_oc = :oc AND hash_archivo = :h"),
                {"oc": str(ocs[0]), "h": hash_archivo}
            ).fetchone()
            if existe:
                raise HTTPException(400, "Este archivo ya fue procesado para esta OC (Archivo duplicado).")

    res = procesar_df_oc(df, master)
    res["meta"]["hash_archivo"] = hash_archivo
    res["meta"]["nombre_archivo"] = file.filename
    return res

@router.post("")
def guardar_orden(body: dict = Body(...), authorization: str = Header(None)):
    user = _require_admin(authorization).get("sub", "admin")
    
    meta = body.get("meta")
    detalles = body.get("detalles")
    dist = body.get("distribucion")
    
    if not meta or not detalles:
        raise HTTPException(400, "Faltan datos para guardar la orden.")
        
    with engine.begin() as conn:
        # Check duplicate
        existe = conn.execute(
            text("SELECT id FROM ordenes_maquila WHERE numero_oc = :oc AND hash_archivo = :h"),
            {"oc": meta["numero_oc"], "h": meta["hash_archivo"]}
        ).fetchone()
        
        if existe:
            raise HTTPException(400, "La orden ya fue registrada.")
            
        # Parse dates safely
        def pdate(s):
            if not s or str(s).lower() == 'nan': return None
            try: return pd.to_datetime(s, dayfirst=True).date()
            except: return None
            
        r = conn.execute(
            text("""
                INSERT INTO ordenes_maquila 
                (numero_oc, nombre_archivo, estado_oc, tipo_orden, fecha_emision, 
                 fecha_inicio_recepcion, fecha_fin_recepcion, usuario_carga, 
                 estado_procesamiento, hash_archivo, activa)
                VALUES
                (:oc, :file, :est, :tipo, :fe, :fi, :ff, :user, :proc, :hash, TRUE)
                RETURNING id
            """),
            {
                "oc": meta["numero_oc"], "file": meta.get("nombre_archivo", ""),
                "est": meta.get("estado_oc"), "tipo": meta.get("tipo_orden"),
                "fe": pdate(meta.get("fecha_emision")), 
                "fi": pdate(meta.get("fecha_inicio_recepcion")),
                "ff": pdate(meta.get("fecha_fin_recepcion")),
                "user": user, "proc": body.get("estado_general", "Pendiente"),
                "hash": meta["hash_archivo"]
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
    # viewers can see
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, numero_oc, fecha_carga, estado_procesamiento, activa,
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
        
        # Para recalcular online el estado real
        master = _get_inventory_and_recipes(conn)
        
    det_list = []
    comp_consolidados = {}
    
    for d in det:
        sku = d.sku
        m = master.get(sku, {})
        # Usar lo guardado para cantidades solicitadas
        sol = d.cantidad_solicitada
        rec = d.cantidad_recibida
        pend = max(0, sol - rec)
        
        # Pero usar el maestro vivo para maquilabilidad
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
                for comp in m["componentes"]:
                    c_sku = comp["sku"]
                    c_qty = comp["qty"] * a_maquilar
                    if c_sku not in comp_consolidados:
                        comp_consolidados[c_sku] = {
                            "sku": c_sku,
                            "nombre": master.get(c_sku, {}).get("nombre", "Desconocido"),
                            "requerido": Decimal('0.0'),
                            "utilizado_por": set()
                        }
                    comp_consolidados[c_sku]["requerido"] += c_qty
                    comp_consolidados[c_sku]["utilizado_por"].add(sku)
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
            "estado_analisis": estado_analisis
        })
        
    comp_list = []
    faltantes = False
    
    for c_sku, data in comp_consolidados.items():
        req = float(data["requerido"])
        stock = master.get(c_sku, {}).get("stock_act", 0)
        falt = max(0, req - stock)
        
        if falt > 0: faltantes = True
        
        comp_list.append({
            "sku": c_sku,
            "nombre": data["nombre"],
            "requerido": req,
            "stock_actual": stock,
            "faltante": falt,
            "utilizado_por": list(data["utilizado_por"])
        })
        
    estado_general = "Preparada"
    if any(d["cantidad_a_maquilar"] > 0 for d in det_list):
        if faltantes:
            estado_general = "Bloqueada por faltantes"
        else:
            estado_general = "En preparación"

    meta_dict = dict(oc._mapping)
    # Sobrescribir el estado con la evaluación en vivo para evitar inconsistencias
    # si el stock cambió después de la carga inicial
    meta_dict["estado_procesamiento"] = estado_general

    return {
        "meta": meta_dict,
        "detalles": det_list,
        "componentes": comp_list,
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
        # Load order
        oc = conn.execute(text("SELECT * FROM ordenes_maquila WHERE id = :id"), {"id": id}).fetchone()
        if not oc: raise HTTPException(404, "OC no encontrada")
        
        # Load distribucion (which is the source of truth for the request)
        dist = conn.execute(text("SELECT * FROM orden_maquila_distribucion WHERE orden_id = :id"), {"id": id}).fetchall()
        if not dist: raise HTTPException(400, "No hay distribución guardada para recalcular")
        
        # Convert to df to reuse logic
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
        
        # We also need to preserve "Modelo" which is in detalle. We can join it or just leave it empty if we don't have it.
        # Actually it's better to fetch from detalle
        det = conn.execute(text("SELECT sku, nombre_producto FROM orden_maquila_detalle WHERE orden_id = :id"), {"id": id}).fetchall()
        nombres = {d.sku: d.nombre_producto for d in det}
        df["Modelo"] = df["SKU"].map(lambda x: nombres.get(x, ""))
        
        master = _get_inventory_and_recipes(conn)
        res = procesar_df_oc(df, master)
        
        # Now update details
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
            
        conn.execute(text("UPDATE ordenes_maquila SET estado_procesamiento = :est WHERE id = :id"), {"est": res["estado_general"], "id": id})
        
    return {"ok": True}
