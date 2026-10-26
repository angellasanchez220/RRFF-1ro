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
        SELECT codigo_femaco, estado
        FROM planificacion_sop
        WHERE codigo_femaco = ANY(:codigos)
    """), {"codigos": codigos}).fetchall()

    encontrados = {str(r[0]).strip().upper() for r in rows}
    faltantes = sorted(set(codigos) - encontrados)
    if faltantes:
        raise ValueError(
            f"Los siguientes códigos internos no existen: {', '.join(faltantes)}"
        )

    descontinuados = [str(r[0]) for r in rows if str(r[1]).upper() in ["DESCONTINUADO", "DESCONTINUADOS"]]
    if descontinuados:
        bad_codigos = ", ".join(descontinuados)
        raise ValueError(f"Los siguientes códigos internos están descontinuados: {bad_codigos}")

@router.get("/recetas")
def get_recetas():
    # Internamente llamamos "recetas" a la ruta por compatibilidad, pero representan Familias
    with engine.connect() as conn:
        try:
            df_recetas = pd.read_sql(text("""
                SELECT 
                    r.id, r.sku_maquilable as identificador, r.descripcion as nombre_familia, r.activa, r.fecha_actualizacion,
                    (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id) as cantidad_miembros
                FROM recetas_maquila r
                ORDER BY r.id DESC
            """), conn)
            
            df_recetas['fecha_actualizacion'] = df_recetas['fecha_actualizacion'].astype(str)
            return {"data": df_recetas.to_dict(orient="records")}
        except Exception as e:
            return {"data": [], "error": str(e)}

@router.get("/recetas/{receta_id}")
def get_receta(receta_id: int):
    with engine.connect() as conn:
        try:
            receta = conn.execute(text("SELECT * FROM recetas_maquila WHERE id = :id"), {"id": receta_id}).fetchone()
            if not receta:
                raise HTTPException(status_code=404, detail="Familia no encontrada")
                
            componentes = pd.read_sql(text("""
                SELECT 
                    c.id,
                    c.sku_componente AS codigo_femaco,
                    p.sku,
                    c.no_transformable,
                    p.nombre_producto
                FROM receta_maquila_componentes c
                LEFT JOIN planificacion_sop p
                       ON TRIM(p.codigo_femaco) = TRIM(c.sku_componente)
                WHERE c.receta_id = :id
            """), conn, params={"id": receta_id})
            
            receta_dict = dict(receta._mapping)
            receta_dict['fecha_creacion'] = str(receta_dict['fecha_creacion'])
            receta_dict['fecha_actualizacion'] = str(receta_dict['fecha_actualizacion'])
            
            comps = componentes.to_dict(orient="records")
            # Convertir booleanos
            for c in comps:
                c['no_transformable'] = bool(c['no_transformable'])
                
            receta_dict['miembros'] = comps
            
            return receta_dict
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/recetas")
def create_receta(body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    nombre_familia = body.get("nombre_familia", "").strip()
    activa = body.get("activa", True)
    miembros = body.get("miembros", [])
    
    if not nombre_familia:
        raise HTTPException(status_code=400, detail="Falta el nombre de la familia")
    if not miembros or len(miembros) < 2:
        raise HTTPException(status_code=400, detail="Debe haber al menos dos códigos internos en la familia")
        
    codigos_miembros = [_codigo_miembro(m) for m in miembros]
    if any(not codigo for codigo in codigos_miembros):
        raise HTTPException(status_code=400, detail="Todos los integrantes deben tener código interno")
    if len(codigos_miembros) != len(set(codigos_miembros)):
        raise HTTPException(status_code=400, detail="Hay códigos internos duplicados en la familia")

    # Identificador dummy para la base de datos
    sku_dummy = f"FAM-{uuid.uuid4().hex[:16].upper()}"

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, codigos_miembros)
                
            result = conn.execute(text("""
                INSERT INTO recetas_maquila (sku_maquilable, descripcion, activa)
                VALUES (:sku, :desc, :activa)
                RETURNING id
            """), {"sku": sku_dummy, "desc": nombre_familia, "activa": activa})
            
            receta_id = result.fetchone()[0]
            
            for m, codigo in zip(miembros, codigos_miembros):
                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (receta_id, sku_componente, cantidad_por_unidad, no_transformable)
                    VALUES (:rid, :skuc, :qty, :nt)
                """), {
                    "rid": receta_id, 
                    "skuc": codigo,
                    "qty": Decimal("1.0"),
                    "nt": bool(m.get("no_transformable", False))
                })
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
    miembros = body.get("miembros", [])
    
    if not nombre_familia or not miembros or len(miembros) < 2:
        raise HTTPException(status_code=400, detail="Datos incompletos o menos de 2 miembros")
        
    codigos_miembros = [_codigo_miembro(m) for m in miembros]
    if any(not codigo for codigo in codigos_miembros):
        raise HTTPException(status_code=400, detail="Todos los integrantes deben tener código interno")
    if len(codigos_miembros) != len(set(codigos_miembros)):
        raise HTTPException(status_code=400, detail="Hay códigos internos duplicados en la familia")

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, codigos_miembros)
            
            conn.execute(text("""
                UPDATE recetas_maquila 
                SET descripcion = :desc, activa = :activa, fecha_actualizacion = NOW()
                WHERE id = :id
            """), {"desc": nombre_familia, "activa": activa, "id": receta_id})
            
            conn.execute(text("DELETE FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": receta_id})
            
            for m, codigo in zip(miembros, codigos_miembros):
                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (receta_id, sku_componente, cantidad_por_unidad, no_transformable)
                    VALUES (:rid, :skuc, :qty, :nt)
                """), {
                    "rid": receta_id, 
                    "skuc": codigo,
                    "qty": Decimal("1.0"),
                    "nt": bool(m.get("no_transformable", False))
                })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
            
    return {"ok": True, "familia_id": receta_id}

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
        WHERE r.activa = TRUE
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

