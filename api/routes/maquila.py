from fastapi import APIRouter, Header, HTTPException, Body
from sqlalchemy import text
import pandas as pd
from datetime import datetime
from decimal import Decimal

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()

def _require_admin(authorization: str):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar recetas")
    return payload

def _check_descontinuados(conn, skus):
    if not skus:
        return
    query = "SELECT sku FROM planificacion_sop WHERE sku IN :skus AND condicion = 'DESCONTINUADO'"
    # In pandas/sqlalchemy, IN clause with tuple works
    rows = conn.execute(text(query).bindparams(skus=tuple(skus))).fetchall()
    if rows:
        bad_skus = ", ".join([r[0] for r in rows])
        raise ValueError(f"Los siguientes SKUs están descontinuados: {bad_skus}")

def _check_cycles(conn, sku_terminado, componentes_skus, ignore_receta_id=None):
    query = """
        SELECT r.sku_maquilable, c.sku_componente
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON r.id = c.receta_id
        WHERE r.activa = TRUE
    """
    if ignore_receta_id:
        query += f" AND r.id != {ignore_receta_id}"
        
    df = pd.read_sql(text(query), conn)
    
    graph = {}
    for _, row in df.iterrows():
        p = row['sku_maquilable']
        c = row['sku_componente']
        graph.setdefault(p, []).append(c)
        
    # Reemplazar/añadir el nodo actual
    graph[sku_terminado] = componentes_skus
    
    def dfs(node, path):
        if node in path:
            return path[path.index(node):] + [node]
        
        path.append(node)
        for child in graph.get(node, []):
            cycle = dfs(child, list(path))
            if cycle:
                return cycle
        return None
        
    for node in list(graph.keys()):
        cycle = dfs(node, [])
        if cycle:
            cycle_str = " -> ".join(cycle)
            raise ValueError(f"No se puede activar la receta porque se genera un ciclo: {cycle_str}")

@router.get("/recetas")
def get_recetas():
    with engine.connect() as conn:
        try:
            df_recetas = pd.read_sql(text("""
                SELECT 
                    r.id, r.sku_maquilable, r.descripcion, r.activa, r.fecha_actualizacion,
                    (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id) as cantidad_componentes,
                    (SELECT nombre_producto FROM planificacion_sop p WHERE p.sku = r.sku_maquilable LIMIT 1) as nombre_producto
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
                raise HTTPException(status_code=404, detail="Receta no encontrada")
                
            componentes = pd.read_sql(text("""
                SELECT 
                    c.id, c.sku_componente, c.cantidad_por_unidad, c.observacion,
                    (SELECT nombre_producto FROM planificacion_sop p WHERE p.sku = c.sku_componente LIMIT 1) as nombre_producto
                FROM receta_maquila_componentes c
                WHERE c.receta_id = :id
            """), conn, params={"id": receta_id})
            
            receta_dict = dict(receta._mapping)
            receta_dict['fecha_creacion'] = str(receta_dict['fecha_creacion'])
            receta_dict['fecha_actualizacion'] = str(receta_dict['fecha_actualizacion'])
            
            comps = componentes.to_dict(orient="records")
            for c in comps:
                c['cantidad_por_unidad'] = float(c['cantidad_por_unidad'])
            receta_dict['componentes'] = comps
            
            return receta_dict
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/recetas")
def create_receta(body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    sku_maquilable = body.get("sku_maquilable")
    descripcion = body.get("descripcion", "")
    activa = body.get("activa", True)
    componentes = body.get("componentes", [])
    
    if not sku_maquilable:
        raise HTTPException(status_code=400, detail="Falta SKU maquilable")
    if not componentes or len(componentes) == 0:
        raise HTTPException(status_code=400, detail="Debe haber al menos un componente")
        
    skus_componentes = [c["sku_componente"] for c in componentes]
    if len(skus_componentes) != len(set(skus_componentes)):
        raise HTTPException(status_code=400, detail="Hay componentes duplicados")
    if sku_maquilable in skus_componentes:
        raise HTTPException(status_code=400, detail="El producto terminado no puede ser componente directo")
        
    for c in componentes:
        if float(c.get("cantidad_por_unidad", 0)) <= 0:
            raise HTTPException(status_code=400, detail=f"Cantidad inválida para {c['sku_componente']}")

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, [sku_maquilable] + skus_componentes)
            
            if activa:
                active_row = conn.execute(text("SELECT id FROM recetas_maquila WHERE sku_maquilable = :sku AND activa = TRUE"), {"sku": sku_maquilable}).fetchone()
                if active_row:
                    raise ValueError("Ya existe una receta activa para este SKU. Desactívela primero.")
                
                _check_cycles(conn, sku_maquilable, skus_componentes)
                
            result = conn.execute(text("""
                INSERT INTO recetas_maquila (sku_maquilable, descripcion, activa)
                VALUES (:sku, :desc, :activa)
                RETURNING id
            """), {"sku": sku_maquilable, "desc": descripcion, "activa": activa})
            
            receta_id = result.fetchone()[0]
            
            for comp in componentes:
                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (receta_id, sku_componente, cantidad_por_unidad)
                    VALUES (:rid, :skuc, :qty)
                """), {
                    "rid": receta_id, 
                    "skuc": comp["sku_componente"], 
                    "qty": Decimal(str(comp["cantidad_por_unidad"]))
                })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
            
    return {"ok": True, "receta_id": receta_id}

@router.put("/recetas/{receta_id}")
def update_receta(receta_id: int, body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    sku_maquilable = body.get("sku_maquilable")
    descripcion = body.get("descripcion", "")
    activa = body.get("activa", True)
    componentes = body.get("componentes", [])
    
    if not sku_maquilable or not componentes:
        raise HTTPException(status_code=400, detail="Datos incompletos")
        
    skus_componentes = [c["sku_componente"] for c in componentes]
    if len(skus_componentes) != len(set(skus_componentes)):
        raise HTTPException(status_code=400, detail="Hay componentes duplicados")
    if sku_maquilable in skus_componentes:
        raise HTTPException(status_code=400, detail="El producto terminado no puede ser componente directo")
        
    for c in componentes:
        if float(c.get("cantidad_por_unidad", 0)) <= 0:
            raise HTTPException(status_code=400, detail=f"Cantidad inválida para {c['sku_componente']}")

    try:
        with engine.begin() as conn:
            _check_descontinuados(conn, [sku_maquilable] + skus_componentes)
            
            if activa:
                active_row = conn.execute(text("SELECT id FROM recetas_maquila WHERE sku_maquilable = :sku AND activa = TRUE AND id != :id"), {"sku": sku_maquilable, "id": receta_id}).fetchone()
                if active_row:
                    raise ValueError("Ya existe una receta activa para este SKU. Desactívela primero.")
                
                _check_cycles(conn, sku_maquilable, skus_componentes, ignore_receta_id=receta_id)
                
            conn.execute(text("""
                UPDATE recetas_maquila 
                SET sku_maquilable = :sku, descripcion = :desc, activa = :activa, fecha_actualizacion = NOW()
                WHERE id = :id
            """), {"sku": sku_maquilable, "desc": descripcion, "activa": activa, "id": receta_id})
            
            conn.execute(text("DELETE FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": receta_id})
            
            for comp in componentes:
                conn.execute(text("""
                    INSERT INTO receta_maquila_componentes (receta_id, sku_componente, cantidad_por_unidad)
                    VALUES (:rid, :skuc, :qty)
                """), {
                    "rid": receta_id, 
                    "skuc": comp["sku_componente"], 
                    "qty": Decimal(str(comp["cantidad_por_unidad"]))
                })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
            
    return {"ok": True, "receta_id": receta_id}

@router.patch("/recetas/{receta_id}/estado")
def toggle_receta_estado(receta_id: int, body: dict = Body(...), authorization: str = Header(None)):
    _require_admin(authorization)
    
    activa = body.get("activa")
    if activa is None:
        raise HTTPException(status_code=400, detail="Falta estado 'activa'")
        
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT sku_maquilable FROM recetas_maquila WHERE id = :id"), {"id": receta_id}).fetchone()
            if not row:
                raise ValueError("Receta no encontrada")
            sku = row[0]
            
            if activa:
                active_row = conn.execute(text("SELECT id FROM recetas_maquila WHERE sku_maquilable = :sku AND activa = TRUE AND id != :id"), {"sku": sku, "id": receta_id}).fetchone()
                if active_row:
                    raise ValueError("Ya existe una receta activa para este SKU. Desactívela primero.")
                
                # Para revisar ciclos, necesitamos los componentes
                comps_rows = conn.execute(text("SELECT sku_componente FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": receta_id}).fetchall()
                _check_descontinuados(conn, [sku] + [c[0] for c in comps_rows])
                _check_cycles(conn, sku, [c[0] for c in comps_rows], ignore_receta_id=receta_id)
                    
            conn.execute(text("UPDATE recetas_maquila SET activa = :activa, fecha_actualizacion = NOW() WHERE id = :id"), {"activa": activa, "id": receta_id})
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
            
    return {"ok": True}

@router.post("/calcular")
def calcular_requerimientos(body: dict = Body(...)):
    receta_id = body.get("receta_id")
    cantidad = body.get("cantidad_a_fabricar")
    
    if not receta_id or not cantidad or float(cantidad) <= 0:
        raise HTTPException(status_code=400, detail="Datos inválidos")
        
    cantidad_d = Decimal(str(cantidad))
        
    with engine.connect() as conn:
        receta = conn.execute(text("SELECT sku_maquilable FROM recetas_maquila WHERE id = :id"), {"id": receta_id}).fetchone()
        if not receta:
            raise HTTPException(status_code=404, detail="Receta no encontrada")
            
        componentes_data = pd.read_sql(text("""
            SELECT 
                c.sku_componente as sku,
                (SELECT nombre_producto FROM planificacion_sop p WHERE p.sku = c.sku_componente LIMIT 1) as nombre,
                c.cantidad_por_unidad,
                COALESCE((SELECT stock_act FROM planificacion_sop p WHERE p.sku = c.sku_componente LIMIT 1), 0) as stock_actual,
                (SELECT ump FROM planificacion_sop p WHERE p.sku = c.sku_componente LIMIT 1) as ump
            FROM receta_maquila_componentes c
            WHERE c.receta_id = :id
        """), conn, params={"id": receta_id})
        
    resultado = {
        "sku_maquilable": receta[0],
        "cantidad_a_fabricar": float(cantidad_d),
        "componentes": []
    }
    
    for _, row in componentes_data.iterrows():
        qty_unit = Decimal(str(row['cantidad_por_unidad']))
        qty_req = cantidad_d * qty_unit
        
        stock_val = row['stock_actual']
        if pd.isna(stock_val): stock_val = 0
        stock = Decimal(str(stock_val))
        
        faltante = qty_req - stock
        if faltante < 0: faltante = Decimal("0")
        
        estado = "Disponible"
        if faltante > 0 and stock > 0:
            estado = "Parcial"
        elif stock <= 0:
            estado = "Sin stock"
            
        # Revisar si requiere ajuste (ej. cantidad decimal pero ump es 1)
        ump_val = row['ump']
        requiere_ajuste = False
        if float(qty_req) != int(qty_req) and ump_val and float(ump_val) == int(ump_val):
            requiere_ajuste = True
            
        resultado["componentes"].append({
            "sku": row['sku'],
            "nombre": row['nombre'] or row['sku'],
            "cantidad_por_unidad": float(qty_unit),
            "cantidad_requerida": float(qty_req),
            "stock_actual": float(stock),
            "faltante": float(faltante),
            "estado": estado,
            "requiere_ajuste": requiere_ajuste
        })
        
    return resultado
