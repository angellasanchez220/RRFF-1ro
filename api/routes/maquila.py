from fastapi import APIRouter, Header, HTTPException, Body
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
