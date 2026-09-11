import sys
import os
import json
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.db import engine
from sqlalchemy import text
from api.routes.maquila import create_receta, update_receta, get_recetas, get_receta
from src.services.maquila_service import build_maquila_families

def query_db():
    with engine.connect() as conn:
        r = conn.execute(text("SELECT id, sku_maquilable, descripcion FROM recetas_maquila ORDER BY id DESC LIMIT 1")).fetchone()
        c = conn.execute(text("SELECT receta_id, sku_componente, no_transformable FROM receta_maquila_componentes WHERE receta_id = :id"), {"id": r.id}).fetchall()
        print(f"\n[BD] recetas_maquila: id={r.id}, sku_maquilable='{r.sku_maquilable}', desc='{r.descripcion}'")
        print("[BD] receta_maquila_componentes:")
        for row in c:
            print(f"  -> sku_componente='{row.sku_componente}', no_transformable={row.no_transformable}")
        return r.id

def test_cases():
    print("Iniciando pruebas de Casos...")
    
    lookup_dict = {
        "SKU1": {"nombre_producto": "P1", "stock_act": 100, "ritmo_mensual": 10},
        "SKU2": {"nombre_producto": "P2", "stock_act": 200, "ritmo_mensual": 20},
        "SKU3": {"nombre_producto": "P3", "stock_act": 300, "ritmo_mensual": 30},
    }

    # Limpiar familia si existía
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM receta_maquila_componentes WHERE sku_componente IN ('SKU1', 'SKU2', 'SKU3')"))
        conn.execute(text("DELETE FROM recetas_maquila WHERE descripcion = 'Test Familia'"))
        
    try:
        # CASO 1: Todos transformables
        print("\n--- CASO 1: SKU1, SKU2, SKU3 (Todos transformables) ---")
        res = create_receta({
            "nombre_familia": "Test Familia",
            "activa": True,
            "miembros": [
                {"sku": "SKU1", "no_transformable": False},
                {"sku": "SKU2", "no_transformable": False},
                {"sku": "SKU3", "no_transformable": False}
            ]
        }, authorization="Bearer test")
        
        rid = query_db()
        
        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)
            
        for s in ["SKU1", "SKU2", "SKU3"]:
            rv = [x["sku"] for x in familias_map[s]["reemplazos_validos"]]
            print(f"Para {s}: reemplazos válidos = {rv}")
            assert s not in rv
            assert len(rv) == 2
            
        # CASO 2: SKU3 no transformable
        print("\n--- CASO 2: SKU3 No transformable ---")
        update_receta(rid, {
            "nombre_familia": "Test Familia",
            "activa": True,
            "miembros": [
                {"sku": "SKU1", "no_transformable": False},
                {"sku": "SKU2", "no_transformable": False},
                {"sku": "SKU3", "no_transformable": True}
            ]
        }, authorization="Bearer test")
        
        query_db()
        
        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)
            
        print(f"Para SKU1: reemplazos = {[x['sku'] for x in familias_map['SKU1']['reemplazos_validos']]}")
        print(f"Para SKU2: reemplazos = {[x['sku'] for x in familias_map['SKU2']['reemplazos_validos']]}")
        print(f"Para SKU3: reemplazos = {[x['sku'] for x in familias_map['SKU3']['reemplazos_validos']]}")
        
        assert "SKU3" not in [x['sku'] for x in familias_map['SKU1']['reemplazos_validos']]
        assert "SKU3" not in [x['sku'] for x in familias_map['SKU2']['reemplazos_validos']]
        assert set([x['sku'] for x in familias_map['SKU3']['reemplazos_validos']]) == {"SKU1", "SKU2"}

        # CASO 3: SKU1 y SKU3 no transformables
        print("\n--- CASO 3: SKU1 y SKU3 No transformables ---")
        update_receta(rid, {
            "nombre_familia": "Test Familia",
            "activa": True,
            "miembros": [
                {"sku": "SKU1", "no_transformable": True},
                {"sku": "SKU2", "no_transformable": False},
                {"sku": "SKU3", "no_transformable": True}
            ]
        }, authorization="Bearer test")
        
        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)
            
        for s in ["SKU1", "SKU2", "SKU3"]:
            print(f"Para {s}: reemplazos = {[x['sku'] for x in familias_map[s]['reemplazos_validos']]}")

        # CASO 4: Todos no transformables
        print("\n--- CASO 4: Todos No transformables ---")
        update_receta(rid, {
            "nombre_familia": "Test Familia",
            "activa": True,
            "miembros": [
                {"sku": "SKU1", "no_transformable": True},
                {"sku": "SKU2", "no_transformable": True},
                {"sku": "SKU3", "no_transformable": True}
            ]
        }, authorization="Bearer test")
        
        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)
            
        for s in ["SKU1", "SKU2", "SKU3"]:
            rv = [x['sku'] for x in familias_map[s]['reemplazos_validos']]
            print(f"Para {s}: reemplazos = {rv}")
            assert len(rv) == 0

        # CASO 5: Stocks
        print("\n--- CASO 5: Comprobar Stocks ---")
        update_receta(rid, {
            "nombre_familia": "Test Familia",
            "activa": True,
            "miembros": [
                {"sku": "SKU1", "no_transformable": False}, # stock 100
                {"sku": "SKU2", "no_transformable": False}, # stock 200
                {"sku": "SKU3", "no_transformable": True}   # stock 300
            ]
        }, authorization="Bearer test")
        with engine.connect() as conn:
            familias_map = build_maquila_families(conn, lookup_dict)
            
        for s in ["SKU1", "SKU2", "SKU3"]:
            print(f"Para {s}: stock bruto total = {familias_map[s]['stock_bruto_familia']}, adicional = {familias_map[s]['stock_reemplazable_adicional']}")
            assert familias_map[s]['stock_bruto_familia'] == 600
        
        # Para SKU1, adicional = SKU2 (200)
        assert familias_map['SKU1']['stock_reemplazable_adicional'] == 200
        # Para SKU3, adicional = SKU1 (100) + SKU2 (200) = 300
        assert familias_map['SKU3']['stock_reemplazable_adicional'] == 300

        # CASO 6: Leer estado desde bd
        print("\n--- CASO 6: Comprobar Lectura BD ---")
        receta_bd = get_receta(rid)
        for m in receta_bd["miembros"]:
            print(f"SKU {m['sku']}, nt = {m['no_transformable']}")
            if m["sku"] == "SKU3": assert m["no_transformable"] == True
            else: assert m["no_transformable"] == False
            
        # CASO 7: Borrado
        print("\n--- CASO 7: Borrado ---")
        from api.routes.maquila import delete_receta
        delete_receta(rid, authorization="Bearer test")
        try:
            get_receta(rid)
        except Exception as e:
            print(f"Al intentar leer receta eliminada: {e}")
            
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    import api.routes.maquila
    api.routes.maquila._require_admin = lambda x: {"role": "admin"}
    test_cases()
