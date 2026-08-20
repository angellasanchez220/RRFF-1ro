import json
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to sys path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from api.main import app
from api.db import engine, run_migrations
from sqlalchemy import text
from api.routes.auth import create_token
import pandas as pd

# Run migrations to ensure tables exist
run_migrations()

client = TestClient(app)

# Tokens
token_admin = create_token({"sub": "admin", "role": "admin", "permisos": {}})
headers_admin = {"Authorization": f"Bearer {token_admin}"}

token_viewer = create_token({"sub": "user1", "role": "viewer", "permisos": {}})
headers_viewer = {"Authorization": f"Bearer {token_viewer}"}

def setup_db():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM receta_maquila_componentes"))
        conn.execute(text("DELETE FROM recetas_maquila"))
        conn.execute(text("DELETE FROM planificacion_sop WHERE sku IN ('PROD-A', 'PROD-B', 'PROD-C', 'INS-B', 'INS-C', 'PROD-DESC', 'INS-DESC')"))
        
        try:
            conn.execute(text("ALTER TABLE planificacion_sop ADD COLUMN IF NOT EXISTS condicion TEXT"))
            conn.execute(text("ALTER TABLE planificacion_sop ADD COLUMN IF NOT EXISTS ump FLOAT"))
        except:
            pass
            
        conn.execute(text("""
            INSERT INTO planificacion_sop (sku, nombre_producto, stock_act, condicion, ump) 
            VALUES 
            ('PROD-A', 'Producto A', 10, 'VIGENTE', 1),
            ('PROD-B', 'Producto B', 5, 'VIGENTE', 1),
            ('PROD-C', 'Producto C', 5, 'VIGENTE', 1),
            ('INS-B', 'Insumo B', 100, 'VIGENTE', 1),
            ('INS-C', 'Insumo C', 50, 'VIGENTE', 1),
            ('PROD-DESC', 'Terminado Descontinuado', 0, 'DESCONTINUADO', 1),
            ('INS-DESC', 'Insumo Descontinuado', 0, 'DESCONTINUADO', 1)
        """))

def teardown_db():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM receta_maquila_componentes"))
        conn.execute(text("DELETE FROM recetas_maquila"))
        conn.execute(text("DELETE FROM planificacion_sop WHERE sku IN ('PROD-A', 'PROD-B', 'PROD-C', 'INS-B', 'INS-C', 'PROD-DESC', 'INS-DESC')"))

def run_tests():
    setup_db()
    
    print("Test 1: Viewer intenta crear receta (Debe fallar)")
    payload = {
        "sku_maquilable": "PROD-A",
        "nombre_receta": "Receta A",
        "activa": True,
        "componentes": [{"sku_componente": "INS-B", "cantidad_por_unidad": 0.5}]
    }
    res = client.post("/api/maquila/recetas", json=payload, headers=headers_viewer)
    assert res.status_code == 403
    print("[OK]")
    
    print("Test 2: Crear receta 1 para PROD-A")
    res = client.post("/api/maquila/recetas", json=payload, headers=headers_admin)
    assert res.status_code == 200
    receta_a_id = res.json()["receta_id"]
    print("[OK]")
    
    print("Test 3: Intentar crear otra receta ACTIVA para PROD-A (Debe fallar)")
    payload_2 = {
        "sku_maquilable": "PROD-A",
        "nombre_receta": "Receta A v2",
        "activa": True,
        "componentes": [{"sku_componente": "INS-C", "cantidad_por_unidad": 1}]
    }
    res = client.post("/api/maquila/recetas", json=payload_2, headers=headers_admin)
    assert res.status_code == 400
    assert "Ya existe una receta activa" in res.json()["detail"]
    print("[OK]")
    
    print("Test 4: Crear otra receta INACTIVA para PROD-A (Debe funcionar)")
    payload_2["activa"] = False
    res = client.post("/api/maquila/recetas", json=payload_2, headers=headers_admin)
    assert res.status_code == 200
    receta_a_v2_id = res.json()["receta_id"]
    print("[OK]")
    
    print("Test 5: Crear receta con componente descontinuado (Debe fallar y hacer rollback)")
    payload_desc = {
        "sku_maquilable": "PROD-B",
        "nombre_receta": "Receta Mala",
        "activa": True,
        "componentes": [{"sku_componente": "INS-DESC", "cantidad_por_unidad": 1}]
    }
    res = client.post("/api/maquila/recetas", json=payload_desc, headers=headers_admin)
    assert res.status_code == 400
    assert "descontinuados" in res.json()["detail"].lower()
    
    # Verificar rollback: no debe existir la receta
    res_list = client.get("/api/maquila/recetas", headers=headers_admin)
    assert not any(r["nombre_receta"] == "Receta Mala" for r in res_list.json()["data"])
    print("[OK]")
    
    print("Test 6: Ciclo simple A -> B -> A")
    # Creamos receta B activa con componente A
    payload_b = {
        "sku_maquilable": "PROD-B",
        "nombre_receta": "Receta B",
        "activa": True,
        "componentes": [{"sku_componente": "PROD-A", "cantidad_por_unidad": 2}]
    }
    res = client.post("/api/maquila/recetas", json=payload_b, headers=headers_admin)
    assert res.status_code == 200
    receta_b_id = res.json()["receta_id"]
    
    # Intentamos editar Receta A para que use PROD-B (generando ciclo A->B->A)
    payload_edit_a = {
        "sku_maquilable": "PROD-A",
        "nombre_receta": "Receta A",
        "activa": True,
        "componentes": [{"sku_componente": "PROD-B", "cantidad_por_unidad": 0.5}]
    }
    res = client.put(f"/api/maquila/recetas/{receta_a_id}", json=payload_edit_a, headers=headers_admin)
    assert res.status_code == 400
    assert "ciclo" in res.json()["detail"].lower()
    print("[OK]")
    
    print("Test 7: Cálculo advierte de ajuste decimal para UMP entera")
    calc_payload = {
        "receta_id": receta_a_id,
        "cantidad_a_fabricar": 11
    }
    # INS-B es 0.5 por unidad. Para 11 unidades son 5.5.
    res = client.post("/api/maquila/calcular", json=calc_payload, headers=headers_viewer)
    assert res.status_code == 200
    data = res.json()
    comp_b = data["componentes"][0]
    assert comp_b["cantidad_requerida"] == 5.5
    assert comp_b["requiere_ajuste"] == True
    print("[OK]")

    print("Test 8: Dashboard muestra datos extras")
    res = client.get("/api/sop/", headers=headers_admin)
    data = res.json()["data"]
    prod_a = next(x for x in data if x["sku"] == "PROD-A")
    assert prod_a["es_maquilable"] == True
    assert prod_a["receta_maquila_id"] == receta_a_id
    assert prod_a["cantidad_componentes_receta"] == 1
    
    prod_b = next(x for x in data if x["sku"] == "PROD-B")
    assert prod_b["receta_maquila_id"] == receta_b_id
    print("[OK]")
    
    teardown_db()
    print("All tests passed.")

if __name__ == "__main__":
    run_tests()
