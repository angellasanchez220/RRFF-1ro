from fastapi import APIRouter, Header, HTTPException, Body
from fastapi.responses import StreamingResponse
import io
import math
from sqlalchemy import text
import pandas as pd
from datetime import datetime
from decimal import Decimal
import time
import uuid

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()

def _require_admin(authorization: str):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar familias")
    return payload

def _codigo_miembro(miembro):
    """Acepta el contrato nuevo y el antiguo, pero siempre retorna CÓD. interno."""
    return str(miembro.get("codigo_femaco") or miembro.get("sku") or "").strip().upper()


def _check_descontinuados(conn, codigos):
    if not codigos:
        return
    rows = conn.execute(text("""
        SELECT codigo_femaco, sku, estado
        FROM planificacion_sop
        WHERE codigo_femaco = ANY(:codigos) OR sku = ANY(:codigos)
    """), {"codigos": codigos}).fetchall()

    descontinuados = []
    for r in rows:
        st = str(r[2] or "").strip().upper()
        if st in ["DESCONTINUADO", "DESCONTINUADOS", "OBSOLETO", "INACTIVO", "INACTIVOS"]:
            descontinuados.append(str(r[0] or r[1]))

    if descontinuados:
        bad_codigos = ", ".join(sorted(set(descontinuados)))
        raise ValueError(f"Los siguientes códigos están descontinuados en catálogo: {bad_codigos}")

@router.get("/recetas")
def get_recetas():
    # Internamente llamamos "recetas" a la ruta por compatibilidad, pero representan Familias y Recetas de Maquila
    with engine.connect() as conn:
        try:
            df_recetas = pd.read_sql(text("""
                SELECT 
                    r.id, 
                    r.sku_maquilable as identificador, 
                    r.descripcion as nombre_familia, 
                    r.activa, 
                    r.fecha_actualizacion,
                    r.tiempo_base_1p_min,
                    COALESCE(r.unidades_base_tiempo, 100) as unidades_base_tiempo,
                    COALESCE(r.costo_hora, 0) as costo_hora,
                    COALESCE(r.costo_maquila_estimado, 0) as costo_maquila_estimado,
                    r.producto_objetivo,
                    (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id) as cantidad_miembros,
                    (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id AND COALESCE(c.tipo_componente, 'PRODUCTO') = 'PRODUCTO') as cantidad_productos,
                    (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id AND COALESCE(c.tipo_componente, 'PRODUCTO') != 'PRODUCTO') as cantidad_materiales,
                    (SELECT COUNT(*) FROM receta_maquila_tiempos t WHERE t.receta_id = r.id) as cantidad_pruebas_tiempo
                FROM recetas_maquila r
                ORDER BY r.id DESC
            """), conn)
            
            df_recetas['fecha_actualizacion'] = df_recetas['fecha_actualizacion'].astype(str)
            df_recetas['costo_hora'] = df_recetas['costo_hora'].fillna(0).astype(float)
            df_recetas['costo_maquila_estimado'] = df_recetas['costo_maquila_estimado'].fillna(0).astype(float)
            return {"data": df_recetas.to_dict(orient="records")}
        except Exception as e:
            return {"data": [], "error": str(e)}

@router.get("/recetas/{receta_id}")
def get_receta(receta_id: int):
    with engine.connect() as conn:
        try:
            receta = conn.execute(text("SELECT * FROM recetas_maquila WHERE id = :id"), {"id": receta_id}).fetchone()
            if not receta:
                raise HTTPException(status_code=404, detail="Familia o receta no encontrada")
                
            componentes = pd.read_sql(text("""
                SELECT 
                    c.id,
                    c.sku_componente AS codigo_femaco,
                    p.sku,
                    COALESCE(NULLIF(TRIM(c.nombre_componente), ''), NULLIF(TRIM(p.nombre_producto), ''), c.sku_componente) AS nombre_producto,
                    COALESCE(NULLIF(TRIM(c.nombre_componente), ''), NULLIF(TRIM(p.nombre_producto), ''), '') AS nombre_componente,
                    COALESCE(c.cantidad_por_unidad, 1.0) AS cantidad_por_unidad,
                    COALESCE(c.tipo_componente, 'PRODUCTO') AS tipo_componente,
                    COALESCE(c.unidad_medida, 'UN') AS unidad_medida,
                    COALESCE(c.costo_unitario, 0) AS costo_unitario,
                    c.no_transformable,
                    COALESCE(c.observacion, '') AS observacion
                FROM receta_maquila_componentes c
                LEFT JOIN planificacion_sop p
                       ON TRIM(p.codigo_femaco) = TRIM(c.sku_componente)
                       OR TRIM(p.sku) = TRIM(c.sku_componente)
                WHERE c.receta_id = :id
                ORDER BY c.id ASC
            """), conn, params={"id": receta_id})

            tiempos = pd.read_sql(text("""
                SELECT 
                    id,
                    receta_id,
                    cantidad_personas,
                    tiempo_minutos,
                    COALESCE(unidades_base, 100) AS unidades_base,
                    COALESCE(observaciones, '') AS observaciones,
                    fecha_registro
                FROM receta_maquila_tiempos
                WHERE receta_id = :id
                ORDER BY cantidad_personas ASC, id ASC
            """), conn, params={"id": receta_id})
            
            receta_dict = dict(receta._mapping)
            receta_dict['fecha_creacion'] = str(receta_dict.get('fecha_creacion'))
            receta_dict['fecha_actualizacion'] = str(receta_dict.get('fecha_actualizacion'))
            if receta_dict.get('tiempo_base_1p_min') is not None:
                receta_dict['tiempo_base_1p_min'] = float(receta_dict['tiempo_base_1p_min'])
            if receta_dict.get('unidades_base_tiempo') is None:
                receta_dict['unidades_base_tiempo'] = 100
            receta_dict['costo_hora'] = float(receta_dict.get('costo_hora') or 0)
            receta_dict['costo_maquila_estimado'] = float(receta_dict.get('costo_maquila_estimado') or 0)
            
            comps = componentes.to_dict(orient="records")
            for c in comps:
                c['no_transformable'] = bool(c['no_transformable'])
                c['cantidad_por_unidad'] = float(c['cantidad_por_unidad'])
                c['costo_unitario'] = float(c.get('costo_unitario') or 0)
                
            receta_dict['miembros'] = comps

            t_list = tiempos.to_dict(orient="records")
            for t in t_list:
                t['tiempo_minutos'] = float(t['tiempo_minutos'])
                t['fecha_registro'] = str(t['fecha_registro'])
            receta_dict['tiempos'] = t_list
            
            return receta_dict
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/recetas")
def create_receta(body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    nombre_familia = body.get("nombre_familia", "").strip()
    activa = body.get("activa", True)
    producto_objetivo = body.get("producto_objetivo", "").strip() or None
    
    tiempo_base_1p_min = body.get("tiempo_base_1p_min")
    if tiempo_base_1p_min is not None and str(tiempo_base_1p_min).strip() != "":
        try:
            tiempo_base_1p_min = float(tiempo_base_1p_min)
        except (ValueError, TypeError):
            tiempo_base_1p_min = None
    else:
        tiempo_base_1p_min = None

    try:
        unidades_base_tiempo = int(body.get("unidades_base_tiempo") or 100)
    except Exception:
        unidades_base_tiempo = 100

    try:
        costo_hora = float(body.get("costo_hora", 0) or 0)
        if costo_hora < 0:
            costo_hora = 0.0
    except Exception:
        costo_hora = 0.0

    try:
        costo_maquila_estimado = float(body.get("costo_maquila_estimado", 0) or 0)
        if costo_maquila_estimado < 0:
            costo_maquila_estimado = 0.0
    except Exception:
        costo_maquila_estimado = 0.0

    miembros = body.get("miembros", [])
    tiempos = body.get("tiempos", [])
    
    if not nombre_familia:
        raise HTTPException(status_code=400, detail="Falta el nombre de la familia o receta")
    if not miembros:
        raise HTTPException(status_code=400, detail="Debe ingresar al menos un integrante o material en la receta")
        
    codigos_miembros = [_codigo_miembro(m) for m in miembros]
    if any(not codigo for codigo in codigos_miembros):
        raise HTTPException(status_code=400, detail="Todos los integrantes y materiales deben tener código")
    if len(codigos_miembros) != len(set(codigos_miembros)):
        raise HTTPException(status_code=400, detail="Hay códigos duplicados en la receta")

    # Identificador dummy para la base de datos
    sku_dummy = f"FAM-{uuid.uuid4().hex[:16].upper()}"

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, codigos_miembros)
                
            result = conn.execute(text("""
                INSERT INTO recetas_maquila (
                    sku_maquilable, descripcion, activa,
                    tiempo_base_1p_min, unidades_base_tiempo,
                    costo_hora, costo_maquila_estimado, producto_objetivo
                )
                VALUES (:sku, :desc, :activa, :tbase, :ubase, :chora, :cmest, :pobj)
                RETURNING id
            """), {
                "sku": sku_dummy, 
                "desc": nombre_familia, 
                "activa": activa,
                "tbase": tiempo_base_1p_min,
                "ubase": unidades_base_tiempo,
                "chora": costo_hora,
                "cmest": costo_maquila_estimado,
                "pobj": producto_objetivo
            })
            
            receta_id = result.fetchone()[0]
            
            for m, codigo in zip(miembros, codigos_miembros):
                qty_val = m.get("cantidad_por_unidad")
                try:
                    qty = Decimal(str(qty_val)) if qty_val is not None and str(qty_val).strip() != "" else Decimal("1.0")
                    if qty <= 0:
                        qty = Decimal("1.0")
                except Exception:
                    qty = Decimal("1.0")

                try:
                    costo_u = Decimal(str(m.get("costo_unitario", 0) or 0))
                    if costo_u < 0:
                        costo_u = Decimal("0.0")
                except Exception:
                    costo_u = Decimal("0.0")

                tipo = str(m.get("tipo_componente") or "PRODUCTO").strip().upper()
                nombre_c = str(m.get("nombre_componente") or m.get("nombre_producto") or "").strip()
                um = str(m.get("unidad_medida") or "UN").strip()
                obs = str(m.get("observacion") or "").strip()
                nt = bool(m.get("no_transformable", False))

                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (
                        receta_id, sku_componente, cantidad_por_unidad, no_transformable,
                        tipo_componente, nombre_componente, unidad_medida, costo_unitario, observacion
                    )
                    VALUES (:rid, :skuc, :qty, :nt, :tipo, :nombre, :um, :costou, :obs)
                """), {
                    "rid": receta_id, 
                    "skuc": codigo,
                    "qty": qty,
                    "nt": nt,
                    "tipo": tipo,
                    "nombre": nombre_c,
                    "um": um,
                    "costou": costo_u,
                    "obs": obs
                })

            for t in tiempos:
                try:
                    p_num = int(t.get("cantidad_personas") or 1)
                    t_min = float(t.get("tiempo_minutos") or 0)
                    ub = int(t.get("unidades_base") or unidades_base_tiempo or 100)
                    t_obs = str(t.get("observaciones") or "").strip()
                    if p_num > 0 and t_min > 0:
                        conn.execute(text("""
                            INSERT INTO receta_maquila_tiempos (
                                receta_id, cantidad_personas, tiempo_minutos, unidades_base, observaciones
                            )
                            VALUES (:rid, :p, :t, :ub, :obs)
                        """), {
                            "rid": receta_id,
                            "p": p_num,
                            "t": t_min,
                            "ub": ub,
                            "obs": t_obs
                        })
                except Exception:
                    pass

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
            
    return {"ok": True, "familia_id": receta_id}

@router.put("/recetas/{receta_id}")
def update_receta(receta_id: int, body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    nombre_familia = body.get("nombre_familia", "").strip()
    activa = body.get("activa", True)
    producto_objetivo = body.get("producto_objetivo", "").strip() or None
    
    tiempo_base_1p_min = body.get("tiempo_base_1p_min")
    if tiempo_base_1p_min is not None and str(tiempo_base_1p_min).strip() != "":
        try:
            tiempo_base_1p_min = float(tiempo_base_1p_min)
        except (ValueError, TypeError):
            tiempo_base_1p_min = None
    else:
        tiempo_base_1p_min = None

    try:
        unidades_base_tiempo = int(body.get("unidades_base_tiempo") or 100)
    except Exception:
        unidades_base_tiempo = 100

    try:
        costo_hora = float(body.get("costo_hora", 0) or 0)
        if costo_hora < 0:
            costo_hora = 0.0
    except Exception:
        costo_hora = 0.0

    try:
        costo_maquila_estimado = float(body.get("costo_maquila_estimado", 0) or 0)
        if costo_maquila_estimado < 0:
            costo_maquila_estimado = 0.0
    except Exception:
        costo_maquila_estimado = 0.0

    miembros = body.get("miembros", [])
    tiempos = body.get("tiempos", [])
    
    if not nombre_familia:
        raise HTTPException(status_code=400, detail="Falta el nombre de la familia o receta")
    if not miembros:
        raise HTTPException(status_code=400, detail="Debe ingresar al menos un integrante o material en la receta")
        
    codigos_miembros = [_codigo_miembro(m) for m in miembros]
    if any(not codigo for codigo in codigos_miembros):
        raise HTTPException(status_code=400, detail="Todos los integrantes y materiales deben tener código")
    if len(codigos_miembros) != len(set(codigos_miembros)):
        raise HTTPException(status_code=400, detail="Hay códigos duplicados en la receta")

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, codigos_miembros)
            
            conn.execute(text("""
                UPDATE recetas_maquila 
                SET descripcion = :desc, 
                    activa = :activa, 
                    tiempo_base_1p_min = :tbase,
                    unidades_base_tiempo = :ubase,
                    costo_hora = :chora,
                    costo_maquila_estimado = :cmest,
                    producto_objetivo = :pobj,
                    fecha_actualizacion = NOW()
                WHERE id = :id
            """), {
                "desc": nombre_familia, 
                "activa": activa, 
                "tbase": tiempo_base_1p_min,
                "ubase": unidades_base_tiempo,
                "chora": costo_hora,
                "cmest": costo_maquila_estimado,
                "pobj": producto_objetivo,
                "id": receta_id
            })
            
            conn.execute(text("DELETE FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": receta_id})
            
            for m, codigo in zip(miembros, codigos_miembros):
                qty_val = m.get("cantidad_por_unidad")
                try:
                    qty = Decimal(str(qty_val)) if qty_val is not None and str(qty_val).strip() != "" else Decimal("1.0")
                    if qty <= 0:
                        qty = Decimal("1.0")
                except Exception:
                    qty = Decimal("1.0")

                try:
                    costo_u = Decimal(str(m.get("costo_unitario", 0) or 0))
                    if costo_u < 0:
                        costo_u = Decimal("0.0")
                except Exception:
                    costo_u = Decimal("0.0")

                tipo = str(m.get("tipo_componente") or "PRODUCTO").strip().upper()
                nombre_c = str(m.get("nombre_componente") or m.get("nombre_producto") or "").strip()
                um = str(m.get("unidad_medida") or "UN").strip()
                obs = str(m.get("observacion") or "").strip()
                nt = bool(m.get("no_transformable", False))

                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (
                        receta_id, sku_componente, cantidad_por_unidad, no_transformable,
                        tipo_componente, nombre_componente, unidad_medida, costo_unitario, observacion
                    )
                    VALUES (:rid, :skuc, :qty, :nt, :tipo, :nombre, :um, :costou, :obs)
                """), {
                    "rid": receta_id, 
                    "skuc": codigo,
                    "qty": qty,
                    "nt": nt,
                    "tipo": tipo,
                    "nombre": nombre_c,
                    "um": um,
                    "costou": costo_u,
                    "obs": obs
                })

            # Sincronizar tiempos
            conn.execute(text("DELETE FROM receta_maquila_tiempos WHERE receta_id = :id"), {"id": receta_id})
            for t in tiempos:
                try:
                    p_num = int(t.get("cantidad_personas") or 1)
                    t_min = float(t.get("tiempo_minutos") or 0)
                    ub = int(t.get("unidades_base") or unidades_base_tiempo or 100)
                    t_obs = str(t.get("observaciones") or "").strip()
                    if p_num > 0 and t_min > 0:
                        conn.execute(text("""
                            INSERT INTO receta_maquila_tiempos (
                                receta_id, cantidad_personas, tiempo_minutos, unidades_base, observaciones
                            )
                            VALUES (:rid, :p, :t, :ub, :obs)
                        """), {
                            "rid": receta_id,
                            "p": p_num,
                            "t": t_min,
                            "ub": ub,
                            "obs": t_obs
                        })
                except Exception:
                    pass

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
            
    return {"ok": True, "familia_id": receta_id}

@router.post("/recetas/{receta_id}/tiempos")
def add_receta_tiempo(receta_id: int, body: dict = Body(...), authorization: str = Header(None)):
    """Permite registrar una nueva prueba de tiempo con N personas para una receta dada."""
    _require_admin(authorization)
    try:
        p = int(body.get("cantidad_personas", 1))
        t = float(body.get("tiempo_minutos", 0))
        ub = int(body.get("unidades_base", 100))
        obs = str(body.get("observaciones", "")).strip()
        if p <= 0 or t <= 0:
            raise HTTPException(400, "Cantidad de personas y tiempo deben ser mayores a 0")
        with engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO receta_maquila_tiempos (receta_id, cantidad_personas, tiempo_minutos, unidades_base, observaciones)
                VALUES (:rid, :p, :t, :ub, :obs)
                RETURNING id, fecha_registro
            """), {"rid": receta_id, "p": p, "t": t, "ub": ub, "obs": obs}).fetchone()
            return {"ok": True, "id": row[0], "fecha_registro": str(row[1])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/recetas/{receta_id}/tiempos/{tiempo_id}")
def delete_receta_tiempo(receta_id: int, tiempo_id: int, authorization: str = Header(None)):
    """Elimina un registro de prueba de tiempo."""
    _require_admin(authorization)
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM receta_maquila_tiempos WHERE id = :tid AND receta_id = :rid"), {"tid": tiempo_id, "rid": receta_id})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.patch("/recetas/{receta_id}/estado")
def toggle_receta_estado(receta_id: int, body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    activa = body.get("activa")
    if activa is None:
        raise HTTPException(status_code=400, detail="Falta estado 'activa'")
        
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE recetas_maquila SET activa = :activa, fecha_actualizacion = NOW() WHERE id = :id"), {"activa": activa, "id": receta_id})
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
            
    return {"ok": True}

@router.delete("/recetas/{receta_id}")
def delete_receta(receta_id: int, authorization: str = Header(None)):
    _require_admin(authorization)
    
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT id FROM recetas_maquila WHERE id = :id"), {"id": receta_id}).fetchone()
            if not row:
                raise ValueError("Familia no encontrada")
                
            conn.execute(text("DELETE FROM receta_maquila_tiempos WHERE receta_id = :id"), {"id": receta_id})
            conn.execute(text("DELETE FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": receta_id})
            conn.execute(text("DELETE FROM recetas_maquila WHERE id = :id"), {"id": receta_id})
            
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"ok": True, "msg": "Familia eliminada correctamente"}


def _calcular_distribucion_homogenea_data(conn):
    """
    Calcula la distribución homogénea de inventario para todas las familias activas.
    Revisa si hay suficientes unidades dentro del grupo familiar para cubrir la demanda
    mediante transformación/maquila. Solo si la familia completa queda en déficit neto,
    el saldo pasa a compra.
    """
    df_familias = pd.read_sql(text("""
        SELECT r.id AS familia_id,
               COALESCE(NULLIF(TRIM(r.descripcion), ''), r.sku_maquilable) AS nombre_familia,
               c.sku_componente,
               COALESCE(c.no_transformable, FALSE) AS no_transformable
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON c.receta_id = r.id
        WHERE r.activa = TRUE AND COALESCE(c.tipo_componente, 'PRODUCTO') = 'PRODUCTO'
        ORDER BY r.id DESC
    """), conn)

    if df_familias.empty:
        return []

    # Cargar datos de planificacion_sop con estado
    df_sop = pd.read_sql(text("""
        SELECT s.sku, s.codigo_femaco, s.nombre_producto,
               COALESCE(NULLIF(TRIM(s.estado), ''), NULLIF(TRIM(p.condicion), ''), NULLIF(TRIM(p.estado), ''), 'ACTIVOS') AS estado,
               COALESCE(s.stock_act, 0) AS stock_act,
               COALESCE(s.cantidad_transito, 0) AS cantidad_transito,
               COALESCE(s.sug_ritmo_futuro, s.sug_ritmo_mensual, 0) AS ritmo_demanda,
               COALESCE(s.sug_target_uds, 0) AS target_uds,
               COALESCE(sugerencia_compra_inmediata_uds, 0) AS sug_compra_inmediata,
               COALESCE(s.ump, 1) AS ump
        FROM planificacion_sop s
        LEFT JOIN dim_productos p ON (s.sku IS NOT NULL AND s.sku = p.sku) OR (s.codigo_femaco IS NOT NULL AND s.codigo_femaco = p.codigo_femaco)
    """), conn)

    sop_by_fem = {}
    sop_by_sku = {}
    for _, r in df_sop.iterrows():
        fem = str(r["codigo_femaco"] or "").strip().upper()
        sku = str(r["sku"] or "").strip().upper()
        data = dict(r)
        if fem: sop_by_fem[fem] = data
        if sku: sop_by_sku[sku] = data

    familias_grouped = {}
    for _, row in df_familias.iterrows():
        fid = int(row["familia_id"])
        fname = str(row["nombre_familia"])
        cod = str(row["sku_componente"]).strip().upper()
        nt = bool(row["no_transformable"])

        if fid not in familias_grouped:
            familias_grouped[fid] = {
                "familia_id": fid,
                "nombre_familia": fname,
                "miembros": []
            }

        sop_data = sop_by_fem.get(cod) or sop_by_sku.get(cod) or {
            "sku": cod,
            "codigo_femaco": cod,
            "nombre_producto": "Producto sin catálogo",
            "estado": "ACTIVOS",
            "stock_act": 0,
            "cantidad_transito": 0,
            "ritmo_demanda": 0,
            "target_uds": 0,
            "sug_compra_inmediata": 0,
            "ump": 1
        }

        estado_raw = str(sop_data.get("estado", "")).strip().upper()
        is_descontinuado = any(k in estado_raw for k in ["DESCONTINUA", "INACTIV"])

        familias_grouped[fid]["miembros"].append({
            "codigo_femaco": cod,
            "sku": sop_data.get("sku", cod),
            "nombre_producto": sop_data.get("nombre_producto", "Desconocido"),
            "no_transformable": nt,
            "estado": estado_raw or "ACTIVOS",
            "es_descontinuado": is_descontinuado,
            "stock_act": float(sop_data.get("stock_act", 0)),
            "cantidad_transito": float(sop_data.get("cantidad_transito", 0)),
            "stock_total": float(sop_data.get("stock_act", 0)) + float(sop_data.get("cantidad_transito", 0)),
            "demanda": float(sop_data.get("target_uds", 0) or sop_data.get("ritmo_demanda", 0)),
            "sug_compra_bruta": float(sop_data.get("sug_compra_inmediata", 0)),
            "ump": max(1, float(sop_data.get("ump", 1) or 1))
        })

    # Procesar distribución homogénea para cada familia
    resultados = []
    for fid, fam in familias_grouped.items():
        miembros = fam["miembros"]
        # Filtrar transformables para el pool familiar
        transformables = [m for m in miembros if not m["no_transformable"]]
        no_transformables = [m for m in miembros if m["no_transformable"]]
        
        total_stock_familia = sum(m["stock_total"] for m in transformables)
        total_demanda_familia = sum(m["demanda"] for m in transformables)
        
        cubre_total = total_stock_familia >= total_demanda_familia
        cobertura_pct = (total_stock_familia / total_demanda_familia * 100.0) if total_demanda_familia > 0 else 100.0

        deficit_neto_familia = max(0.0, total_demanda_familia - total_stock_familia)
        superavit_neto_familia = max(0.0, total_stock_familia - total_demanda_familia)

        # Regla de negocio:
        # "Siempre a no ser que el artículo que cede esté descontinuado, en ese caso cede todo"
        descontinuados = [m for m in transformables if m.get("es_descontinuado")]
        activos = [m for m in transformables if not m.get("es_descontinuado")]
        
        stock_cedido_descontinuados = sum(m["stock_total"] for m in descontinuados)
        asignaciones = {}
        
        # 1. Los descontinuados ceden el 100% de su stock a los hermanos activos para liquidación
        for d in descontinuados:
            asignaciones[d["codigo_femaco"]] = {
                "stock_asignado": 0.0,
                "saldo_transf": -d["stock_total"],
                "cobertura": 100.0 if d["demanda"] == 0 else 0.0,
                "compra": 0,
                "cubierto": True,
                "obs": "Descontinuado: cede 100% de stock a hermanos activos para liquidación"
            }

        # 2. Distribución entre miembros activos
        activos_con_demanda = [a for a in activos if a["demanda"] > 0]
        activos_sin_demanda = [a for a in activos if a["demanda"] == 0]

        if not activos_con_demanda:
            # Caso donde ningún activo tiene demanda proyectada: conservan su stock
            for a in activos:
                asignaciones[a["codigo_femaco"]] = {
                    "stock_asignado": a["stock_total"],
                    "saldo_transf": 0.0,
                    "cobertura": 100.0,
                    "compra": 0,
                    "cubierto": True,
                    "obs": "Activo sin demanda proyectada: conserva su stock"
                }
        else:
            # Hay activos con demanda proyectada
            # ¿Cuánto déficit tienen los activos con demanda para llegar a su 100%?
            deficit_necesario_activos = sum(max(0.0, a["demanda"] - a["stock_total"]) for a in activos_con_demanda)
            
            # Se cubre primero con el stock de los descontinuados
            deficit_restante_por_cubrir = max(0.0, deficit_necesario_activos - stock_cedido_descontinuados)
            
            # Si aún falta para cubrir el déficit de los activos, los activos sin demanda ceden SOLO LO NECESARIO
            stock_activos_sin_demanda = sum(a["stock_total"] for a in activos_sin_demanda)
            aporte_activos_sin_demanda = min(stock_activos_sin_demanda, deficit_restante_por_cubrir)
            
            # Asignar a activos sin demanda (solo ceden lo estrictamente necesario y conservan el resto de resguardo)
            for a in activos_sin_demanda:
                if stock_activos_sin_demanda > 0 and aporte_activos_sin_demanda > 0:
                    cede = aporte_activos_sin_demanda * (a["stock_total"] / stock_activos_sin_demanda)
                else:
                    cede = 0.0
                stock_conserva = a["stock_total"] - cede
                asignaciones[a["codigo_femaco"]] = {
                    "stock_asignado": round(stock_conserva, 1),
                    "saldo_transf": round(-cede, 1),
                    "cobertura": 100.0,
                    "compra": 0,
                    "cubierto": True,
                    "obs": f"Activo sin demanda: cede {round(cede, 1)} uds necesarias y conserva {round(stock_conserva, 1)} uds de resguardo" if cede > 0 else "Activo sin demanda: conserva 100% de su stock"
                }

            # Stock disponible final para los activos con demanda
            stock_para_activos_con_demanda = sum(a["stock_total"] for a in activos_con_demanda) + stock_cedido_descontinuados + aporte_activos_sin_demanda
            demanda_activos_con_demanda = sum(a["demanda"] for a in activos_con_demanda)
            
            alcanza_activos_con_demanda = stock_para_activos_con_demanda >= demanda_activos_con_demanda
            
            if alcanza_activos_con_demanda:
                # Caso de cobertura completa o superávit:
                # Reparto homogéneo proporcional a la demanda para que se acaben en simultáneo
                ratio_cob = stock_para_activos_con_demanda / demanda_activos_con_demanda
                for a in activos_con_demanda:
                    stock_asig = a["demanda"] * ratio_cob
                    saldo = stock_asig - a["stock_total"]
                    asignaciones[a["codigo_femaco"]] = {
                        "stock_asignado": round(stock_asig, 1),
                        "saldo_transf": round(saldo, 1),
                        "cobertura": 100.0,
                        "compra": 0,
                        "cubierto": True,
                        "obs": "Cubierto 100% por stock familiar (Maquila)"
                    }
            else:
                # Caso de déficit familiar: reparto homogéneo proporcional
                ratio_cob = stock_para_activos_con_demanda / demanda_activos_con_demanda if demanda_activos_con_demanda > 0 else 0
                for a in activos_con_demanda:
                    stock_asig = a["demanda"] * ratio_cob
                    saldo = stock_asig - a["stock_total"]
                    falta = max(0.0, a["demanda"] - stock_asig)
                    compra = math.ceil(falta / a["ump"]) * a["ump"] if falta > 0 else 0
                    cob_pct = round((stock_asig / a["demanda"] * 100) if a["demanda"] > 0 else 100.0, 1)
                    asignaciones[a["codigo_femaco"]] = {
                        "stock_asignado": round(stock_asig, 1),
                        "saldo_transf": round(saldo, 1),
                        "cobertura": cob_pct,
                        "compra": int(compra),
                        "cubierto": False,
                        "obs": f"Déficit familiar: se distribuye stock disponible (cobertura {cob_pct}%) y requiere comprar {int(compra)} uds"
                    }

        miembros_procesados = []
        for m in miembros:
            if m["no_transformable"]:
                stock_res = m["stock_total"]
                compra_m = max(0.0, m["demanda"] - m["stock_total"])
                miembros_procesados.append({
                    **m,
                    "stock_asignado_homogeneo": stock_res,
                    "saldo_transformacion": 0.0,
                    "cobertura_post_distribucion_pct": round((stock_res / m["demanda"] * 100) if m["demanda"] > 0 else 100.0, 1),
                    "compra_remanente_sugerida": math.ceil(compra_m / m["ump"]) * m["ump"] if compra_m > 0 else 0,
                    "cubierto_por_maquila": False,
                    "observacion": "No transformable (gestión individual)"
                })
            else:
                asig = asignaciones.get(m["codigo_femaco"], {})
                miembros_procesados.append({
                    **m,
                    "stock_asignado_homogeneo": asig.get("stock_asignado", m["stock_total"]),
                    "saldo_transformacion": asig.get("saldo_transf", 0.0),
                    "cobertura_post_distribucion_pct": asig.get("cobertura", 100.0),
                    "compra_remanente_sugerida": asig.get("compra", 0),
                    "cubierto_por_maquila": asig.get("cubierto", False),
                    "observacion": asig.get("obs", "")
                })

        total_compra_familia = sum(m["compra_remanente_sugerida"] for m in miembros_procesados)

        resultados.append({
            "familia_id": fid,
            "nombre_familia": fam["nombre_familia"],
            "cantidad_miembros": len(miembros),
            "total_stock_familia": round(total_stock_familia, 1),
            "total_demanda_familia": round(total_demanda_familia, 1),
            "cubre_con_stock_familiar": cubre_total,
            "cobertura_pct": round(cobertura_pct, 1),
            "deficit_neto_familia": round(deficit_neto_familia, 1),
            "superavit_neto_familia": round(superavit_neto_familia, 1),
            "total_compra_remanente_sugerida": total_compra_familia,
            "miembros": miembros_procesados
        })

    return resultados


@router.get("/distribucion-homogenea")
def get_distribucion_homogenea():
    """Retorna el análisis de distribución homogénea de inventario familiar y maquila."""
    with engine.connect() as conn:
        data = _calcular_distribucion_homogenea_data(conn)
        return {"data": data}


@router.get("/export-distribucion")
def export_distribucion_homogenea_excel():
    """Descarga el Plan de Distribución Homogénea y Maquila en Excel."""
    with engine.connect() as conn:
        familias_data = _calcular_distribucion_homogenea_data(conn)
        if not familias_data:
            raise HTTPException(status_code=404, detail="No hay familias activas para exportar")

        # Hoja 1: Resumen Familias
        resumen_rows = []
        # Hoja 2: Detalle Miembros
        detalle_rows = []

        for f in familias_data:
            resumen_rows.append({
                "ID Familia": f["familia_id"],
                "Nombre Familia": f["nombre_familia"],
                "Miembros": f["cantidad_miembros"],
                "Stock Total Familia": f["total_stock_familia"],
                "Demanda Total Familia": f["total_demanda_familia"],
                "Cobertura Familiar (%)": f["cobertura_pct"],
                "¿Cubre Demanda con Stock?": "SÍ (100% Maquila)" if f["cubre_con_stock_familiar"] else "NO (Requiere compra)",
                "Déficit Neto Familia": f["deficit_neto_familia"],
                "Superávit Neto Familia": f["superavit_neto_familia"],
                "Compra Final Sugerida (Uds)": f["total_compra_remanente_sugerida"]
            })

            for m in f["miembros"]:
                transf = m["saldo_transformacion"]
                accion = "Sin cambio"
                if transf > 0:
                    accion = f"Recibir {int(transf)} uds de hermanos (Maquilar)"
                elif transf < 0:
                    accion = f"Ceder {abs(int(transf))} uds para maquila de hermanos"

                detalle_rows.append({
                    "Familia": f["nombre_familia"],
                    "Cód. Interno": m["codigo_femaco"],
                    "SKU": m["sku"],
                    "Producto": m["nombre_producto"],
                    "Estado": m.get("estado", "ACTIVOS"),
                    "Descontinuado": "SÍ" if m.get("es_descontinuado") else "NO",
                    "No Transformable": "SÍ" if m["no_transformable"] else "NO",
                    "Stock Actual": m["stock_act"],
                    "Tránsito": m["cantidad_transito"],
                    "Stock Inicial Total": m["stock_total"],
                    "Demanda / Target (Uds)": m["demanda"],
                    "Stock Post-Distribución Homogénea": m["stock_asignado_homogeneo"],
                    "Saldo Transformación": transf,
                    "Acción Maquila Recomendada": accion,
                    "Cobertura Lograda (%)": m["cobertura_post_distribucion_pct"],
                    "Compra Final Sugerida (Uds)": m["compra_remanente_sugerida"],
                    "Cubierto por Maquila": "SÍ" if m["cubierto_por_maquila"] else "NO",
                    "Observación": m["observacion"]
                })

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(resumen_rows).to_excel(writer, sheet_name="Resumen Familias", index=False)
            pd.DataFrame(detalle_rows).to_excel(writer, sheet_name="Plan Detallado Maquila", index=False)

        output.seek(0)
        filename = f"Plan_Distribucion_Homogenea_Maquila_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@router.get("/simulador")
def simular_maquila(sku: Optional[str] = None):
    """
    Calcula en tiempo real la capacidad máxima de maquila para un SKU dado (o todas las recetas),
    evaluando los stocks actuales de productos hermanos en SOP y los stocks de materiales
    en materiales_maquila, identificando el cuello de botella exacto.
    """
    with engine.connect() as conn:
        # 1. Cargar stock de SOP
        df_sop = pd.read_sql(text("""
            SELECT sku, codigo_femaco, nombre_producto, stock_act 
            FROM planificacion_sop
        """), conn)
        sop_stock = {}
        sop_nombres = {}
        for _, r in df_sop.iterrows():
            s = str(r["sku"] or "").strip().upper()
            f = str(r["codigo_femaco"] or "").strip().upper()
            stk = float(r["stock_act"] or 0)
            nom = str(r["nombre_producto"] or "")
            if s:
                sop_stock[s] = stk
                sop_nombres[s] = nom
            if f:
                sop_stock[f] = stk
                sop_nombres[f] = nom

        # 2. Cargar stock de Materiales Maquila
        df_mat = pd.read_sql(text("""
            SELECT sku, nombre, stock_actual, stock_minimo, costo_unitario, unidad_medida, categoria 
            FROM materiales_maquila WHERE activo = TRUE
        """), conn)
        mat_stock = {}
        for _, r in df_mat.iterrows():
            ms = str(r["sku"]).strip().upper()
            mat_stock[ms] = {
                "sku": ms,
                "nombre": r["nombre"] or "Insumo",
                "stock_actual": float(r["stock_actual"] or 0),
                "stock_minimo": float(r["stock_minimo"] or 0),
                "costo_unitario": float(r["costo_unitario"] or 0),
                "unidad_medida": r["unidad_medida"] or "UN",
                "categoria": r["categoria"] or "INSUMO"
            }

        # 3. Cargar Recetas activas
        query_rec = """
            SELECT id, sku_maquilable, descripcion, tiempo_base_1p_min, unidades_base_tiempo, costo_hora, costo_maquila_estimado, producto_objetivo
            FROM recetas_maquila WHERE activa = TRUE
        """
        df_rec = pd.read_sql(text(query_rec), conn)
        if df_rec.empty:
            return {"ok": True, "data": []}

        rec_ids = df_rec["id"].tolist()
        df_comp = pd.read_sql(text("""
            SELECT receta_id, sku_componente, cantidad_por_unidad, tipo_componente, nombre_componente, unidad_medida, costo_unitario, no_transformable
            FROM receta_maquila_componentes WHERE receta_id = ANY(:ids)
        """), conn, params={"ids": rec_ids})

    comps_by_rec = {}
    for _, c in df_comp.iterrows():
        rid = int(c["receta_id"])
        comps_by_rec.setdefault(rid, []).append({
            "sku": str(c["sku_componente"]).strip().upper(),
            "qty": float(c["cantidad_por_unidad"] or 1),
            "tipo": str(c["tipo_componente"] or "PRODUCTO").strip().upper(),
            "nombre": str(c["nombre_componente"] or ""),
            "um": str(c["unidad_medida"] or "UN"),
            "costo_unitario": float(c["costo_unitario"] or 0),
            "no_transformable": bool(c["no_transformable"])
        })

    resultados = []
    target_sku = sku.strip().upper() if sku else None

    for _, rec in df_rec.iterrows():
        rid = int(rec["id"])
        comps = comps_by_rec.get(rid, [])
        mats = [c for c in comps if c["tipo"] == "MATERIAL"]
        prods = [c for c in comps if c["tipo"] != "MATERIAL"]

        candidatos_skus = set()
        for p in prods:
            candidatos_skus.add(p["sku"])
        if rec["sku_maquilable"]:
            candidatos_skus.add(str(rec["sku_maquilable"]).strip().upper())
        if rec["producto_objetivo"]:
            candidatos_skus.add(str(rec["producto_objetivo"]).strip().upper())

        if target_sku and target_sku not in candidatos_skus:
            continue

        skus_a_evaluar = [target_sku] if target_sku else list(candidatos_skus)

        for p_sku in skus_a_evaluar:
            p_nombre = sop_nombres.get(p_sku, f"Producto {p_sku}")
            p_stock_actual = sop_stock.get(p_sku, 0)

            # Hermanos disponibles
            hermanos_disp = []
            capacidad_por_hermanos = 0.0

            for h in prods:
                if h["sku"] == p_sku or h["no_transformable"]:
                    continue
                h_sku = h["sku"]
                h_stk = sop_stock.get(h_sku, 0)
                h_qty = h["qty"] if h["qty"] > 0 else 1.0
                h_equiv = math.floor(h_stk / h_qty)
                capacidad_por_hermanos += h_equiv
                hermanos_disp.append({
                    "sku": h_sku,
                    "nombre": sop_nombres.get(h_sku, h["nombre"] or "Hermano"),
                    "stock_actual": h_stk,
                    "ratio": h_qty,
                    "unidades_producibles": h_equiv
                })

            # Materiales e insumos requeridos
            materiales_eval = []
            capacidad_por_materiales = float('inf')
            cuello_material = None

            for m in mats:
                m_sku = m["sku"]
                m_info = mat_stock.get(m_sku, {})
                m_stk = m_info.get("stock_actual", 0)
                m_cost = m["costo_unitario"] or m_info.get("costo_unitario", 0)
                m_qty = m["qty"] if m["qty"] > 0 else 1.0
                m_max = math.floor(m_stk / m_qty)

                if m_max < capacidad_por_materiales:
                    capacidad_por_materiales = m_max
                    cuello_material = {
                        "tipo": "MATERIAL",
                        "sku": m_sku,
                        "nombre": m_info.get("nombre", m["nombre"]),
                        "stock_actual": m_stk,
                        "requerido_por_unidad": m_qty,
                        "max_posible": m_max
                    }

                materiales_eval.append({
                    "sku": m_sku,
                    "nombre": m_info.get("nombre", m["nombre"] or "Insumo"),
                    "stock_actual": m_stk,
                    "stock_minimo": m_info.get("stock_minimo", 0),
                    "unidad_medida": m.get("um") or m_info.get("unidad_medida", "UN"),
                    "costo_unitario": m_cost,
                    "ratio": m_qty,
                    "max_posible": m_max
                })

            if capacidad_por_materiales == float('inf'):
                capacidad_por_materiales = capacidad_por_hermanos

            max_producible = min(capacidad_por_hermanos, capacidad_por_materiales)

            if max_producible == 0:
                if capacidad_por_hermanos == 0 and capacidad_por_materiales == 0:
                    cuello_global = {"tipo": "GENERAL", "motivo": "Sin stock de hermanos ni insumos"}
                elif capacidad_por_hermanos == 0:
                    cuello_global = {"tipo": "PRODUCTO", "motivo": "Sin stock de productos hermanos transformables"}
                else:
                    cuello_global = cuello_material or {"tipo": "MATERIAL", "motivo": "Falta stock de insumos"}
            elif capacidad_por_materiales < capacidad_por_hermanos:
                cuello_global = cuello_material
            elif capacidad_por_hermanos < capacidad_por_materiales:
                cuello_global = {
                    "tipo": "PRODUCTO",
                    "motivo": f"Limitado por stock total de hermanos ({capacidad_por_hermanos} uds)",
                    "max_posible": capacidad_por_hermanos
                }
            else:
                cuello_global = cuello_material or {"tipo": "BALANCEADO", "motivo": "Stock balanceado", "max_posible": max_producible}

            t_base = float(rec["tiempo_base_1p_min"] or 45)
            u_base = float(rec["unidades_base_tiempo"] or 100)
            c_hora = float(rec["costo_hora"] or 0)
            vel_uds_h = (u_base / t_base) * 60 if t_base > 0 else 100.0

            horas_1p = round(max_producible / vel_uds_h, 2) if max_producible > 0 else 0.0
            costo_mo = round(horas_1p * c_hora, 2)
            costo_insumos = round(sum(m["costo_unitario"] * m["ratio"] * max_producible for m in materiales_eval), 2)
            costo_total = round(costo_mo + costo_insumos, 2)
            costo_u_maquila = round(costo_total / max_producible, 2) if max_producible > 0 else 0.0

            if cuello_material:
                for me in materiales_eval:
                    me["es_cuello_botella"] = (me["sku"] == cuello_material.get("sku") and me["max_posible"] == max_producible)

            resultados.append({
                "receta_id": rid,
                "familia_nombre": rec["descripcion"] or rec["sku_maquilable"],
                "sku": p_sku,
                "nombre": p_nombre,
                "stock_actual": p_stock_actual,
                "max_producible": int(max_producible),
                "cuello_de_botella": cuello_global,
                "capacidad_por_hermanos": int(capacidad_por_hermanos),
                "capacidad_por_materiales": int(capacidad_por_materiales if capacidad_por_materiales != float('inf') else 0),
                "hermanos_disponibles": hermanos_disp,
                "materiales_evaluacion": materiales_eval,
                "costeo_lote": {
                    "unidades": int(max_producible),
                    "costo_insumos": costo_insumos,
                    "costo_mano_obra": costo_mo,
                    "costo_total": costo_total,
                    "costo_unitario_maquila": costo_u_maquila,
                    "horas_1p": horas_1p,
                    "horas_3p": round(horas_1p / 2.7, 2),
                    "horas_6p": round(horas_1p / 5.2, 2),
                    "velocidad_uds_h": round(vel_uds_h, 1)
                }
            })

    return {"ok": True, "data": resultados}

