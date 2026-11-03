"""
api/routes/kardex.py — Trazabilidad y Libro de Movimientos de Inventario (Kardex)
==============================================================================
Registra y audita todas las entradas, salidas, ajustes de conteo físico y mermas
tanto para Insumos/Materiales de Maquila como para Productos Terminados.
"""

from fastapi import APIRouter, Header, HTTPException, Body, Depends
from typing import Optional, List, Dict, Any
from decimal import Decimal
import pandas as pd
from sqlalchemy import text

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header, require_admin, require_permission

router = APIRouter()


def registrar_movimiento_kardex(
    conn,
    tipo_entidad: str,
    sku: str,
    nombre: str,
    tipo_movimiento: str,
    referencia_doc: str,
    cantidad: float,
    saldo_anterior: float,
    saldo_nuevo: float,
    costo_unitario: float = 0.0,
    motivo: str = "",
    usuario: str = "sistema"
):
    """
    Función auxiliar para registrar movimientos en el Kardex.
    tipo_entidad: 'MATERIAL' | 'PRODUCTO'
    tipo_movimiento: 'INICIAL' | 'ENTRADA_COMPRA' | 'SALIDA_MAQUILA' | 'ENTRADA_MAQUILA' | 'MERMA_MAQUILA' | 'AJUSTE_INVENTARIO'
    """
    conn.execute(text("""
        INSERT INTO inventario_kardex_movimientos (
            tipo_entidad, sku, nombre, tipo_movimiento, referencia_doc,
            cantidad, saldo_anterior, saldo_nuevo, costo_unitario, motivo, usuario
        ) VALUES (
            :tipo_entidad, :sku, :nombre, :tipo_mov, :ref_doc,
            :cantidad, :saldo_ant, :saldo_nuevo, :costo_u, :motivo, :usuario
        )
    """), {
        "tipo_entidad": tipo_entidad.upper().strip(),
        "sku": str(sku).strip().upper(),
        "nombre": str(nombre or "").strip(),
        "tipo_mov": str(tipo_movimiento).strip().upper(),
        "ref_doc": str(referencia_doc or "S/R").strip(),
        "cantidad": round(float(cantidad), 2),
        "saldo_ant": round(float(saldo_anterior), 2),
        "saldo_nuevo": round(float(saldo_nuevo), 2),
        "costo_u": round(float(costo_unitario or 0), 2),
        "motivo": str(motivo or "").strip(),
        "usuario": str(usuario or "sistema").strip()
    })


@router.get("")
def list_movimientos_kardex(
    sku: Optional[str] = None,
    tipo_entidad: Optional[str] = None,
    tipo_movimiento: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    limit: int = 300
):
    """Lista el historial de movimientos de inventario con filtros."""
    with engine.connect() as conn:
        query = "SELECT * FROM inventario_kardex_movimientos WHERE 1=1"
        params = {}

        if sku and sku.strip():
            query += " AND UPPER(sku) = :sku"
            params["sku"] = sku.strip().upper()

        if tipo_entidad and tipo_entidad.strip() and tipo_entidad.upper() != "ALL":
            query += " AND UPPER(tipo_entidad) = :te"
            params["te"] = tipo_entidad.strip().upper()

        if tipo_movimiento and tipo_movimiento.strip() and tipo_movimiento.upper() != "ALL":
            query += " AND UPPER(tipo_movimiento) = :tm"
            params["tm"] = tipo_movimiento.strip().upper()

        if desde and desde.strip():
            query += " AND fecha_movimiento >= :desde"
            params["desde"] = desde.strip()

        if hasta and hasta.strip():
            query += " AND fecha_movimiento <= :hasta"
            params["hasta"] = hasta.strip()

        query += " ORDER BY fecha_movimiento DESC, id DESC LIMIT :limit"
        params["limit"] = min(1000, max(1, limit))

        df = pd.read_sql(text(query), conn, params=params)

    if df.empty:
        return {
            "ok": True,
            "data": [],
            "total": 0,
            "resumen": {
                "total_entradas": 0.0,
                "total_salidas": 0.0,
                "total_mermas": 0.0
            }
        }

    df["fecha_movimiento"] = df["fecha_movimiento"].astype(str)
    records = df.to_dict(orient="records")

    total_entradas = sum(float(r["cantidad"]) for r in records if float(r["cantidad"]) > 0 and r["tipo_movimiento"] != "MERMA_MAQUILA")
    total_salidas = sum(abs(float(r["cantidad"])) for r in records if float(r["cantidad"]) < 0 and r["tipo_movimiento"] != "MERMA_MAQUILA")
    total_mermas = sum(abs(float(r["cantidad"])) for r in records if r["tipo_movimiento"] == "MERMA_MAQUILA")

    return {
        "ok": True,
        "data": records,
        "total": len(records),
        "resumen": {
            "total_entradas": round(total_entradas, 2),
            "total_salidas": round(total_salidas, 2),
            "total_mermas": round(total_mermas, 2)
        }
    }


@router.post("/ajuste")
def registrar_ajuste_inventario(
    body: dict = Body(...),
    authorization: str = Header(None)
):
    """
    Ajuste manual de inventario (Conteo Físico, Cuadratura, Merma o Rotura).
    Actualiza el stock y guarda el registro auditado en el Kardex.
    """
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    user = payload.get("sub", "admin")

    tipo_entidad = str(body.get("tipo_entidad") or "MATERIAL").strip().upper()
    sku = str(body.get("sku") or "").strip().upper()
    nuevo_stock = float(body.get("nuevo_stock") if body.get("nuevo_stock") is not None else -1)
    motivo = str(body.get("motivo") or "").strip()
    referencia_doc = str(body.get("referencia_doc") or "AJUSTE-MANUAL").strip()

    if not sku:
        raise HTTPException(400, "El SKU es obligatorio")
    if nuevo_stock < 0:
        raise HTTPException(400, "El nuevo stock debe ser mayor o igual a 0")
    if not motivo:
        raise HTTPException(400, "El motivo del ajuste es obligatorio para auditoría")

    with engine.begin() as conn:
        if tipo_entidad == "MATERIAL":
            row = conn.execute(text("""
                SELECT sku, nombre, stock_actual, costo_unitario 
                FROM materiales_maquila 
                WHERE UPPER(sku) = :sku
            """), {"sku": sku}).fetchone()

            if not row:
                raise HTTPException(404, f"Material con SKU '{sku}' no encontrado en catálogo")

            saldo_anterior = float(row.stock_actual or 0)
            costo_u = float(row.costo_unitario or 0)
            nombre = row.nombre

            conn.execute(text("""
                UPDATE materiales_maquila
                SET stock_actual = :stock, fecha_actualizacion = NOW()
                WHERE UPPER(sku) = :sku
            """), {"stock": nuevo_stock, "sku": sku})

        else:
            # PRODUCTO en planificacion_sop
            row = conn.execute(text("""
                SELECT sku, nombre_producto, stock_act 
                FROM planificacion_sop 
                WHERE UPPER(sku) = :sku OR UPPER(codigo_femaco) = :sku
            """), {"sku": sku}).fetchone()

            if not row:
                raise HTTPException(404, f"Producto con SKU '{sku}' no encontrado en planificacion_sop")

            saldo_anterior = float(row.stock_act or 0)
            costo_u = 0.0
            nombre = row.nombre_producto

            conn.execute(text("""
                UPDATE planificacion_sop
                SET stock_act = :stock
                WHERE UPPER(sku) = :sku OR UPPER(codigo_femaco) = :sku
            """), {"stock": nuevo_stock, "sku": sku})

        delta = round(nuevo_stock - saldo_anterior, 2)

        registrar_movimiento_kardex(
            conn=conn,
            tipo_entidad=tipo_entidad,
            sku=sku,
            nombre=nombre,
            tipo_movimiento="AJUSTE_INVENTARIO",
            referencia_doc=referencia_doc,
            cantidad=delta,
            saldo_anterior=saldo_anterior,
            saldo_nuevo=nuevo_stock,
            costo_unitario=costo_u,
            motivo=motivo,
            usuario=user
        )

    return {
        "ok": True,
        "sku": sku,
        "saldo_anterior": saldo_anterior,
        "saldo_nuevo": nuevo_stock,
        "delta": delta,
        "mensaje": f"Ajuste registrado exitosamente para {sku} ({delta:+g} uds)"
    }
