import pandas as pd
from sqlalchemy import text

def build_maquila_families(conn, lookup_dict):
    """
    Construye las familias utilizables (dirigidas y recursivas) para todos los SKU
    involucrados en recetas de maquila activas.
    
    :param conn: Conexión a la BD (sqlalchemy).
    :param lookup_dict: Diccionario lookup de SKU a datos: 
           {"SKU1": {"nombre_producto": "X", "stock_act": 100, "ritmo_mensual": 50}, ...}
    :return: dict con el resultado por SKU.
             {"SKU1": {"familia_maquila": [...], "stock_total_familia_maquila": 250}, ...}
    """
    df_comp = pd.read_sql(text("""
        SELECT r.sku_maquilable AS sku_padre,
               c.sku_componente
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON c.receta_id = r.id
        WHERE r.activa = True
    """), conn)
    
    # Construir grafo de adyacencia dirigido (Padre -> [Hijos])
    grafo = {}
    todos_skus_involucrados = set()
    
    for _, row in df_comp.iterrows():
        padre = str(row["sku_padre"])
        hijo = str(row["sku_componente"])
        
        if padre not in grafo:
            grafo[padre] = set()
        grafo[padre].add(hijo)
        
        todos_skus_involucrados.add(padre)
        todos_skus_involucrados.add(hijo)
        
    resultado = {}
    
    def get_info(s):
        info = lookup_dict.get(s, {})
        return {
            "sku": s,
            "nombre_producto": info.get("nombre_producto", "Desconocido"),
            "stock_act": float(info.get("stock_act", 0)),
            "ritmo_mensual": float(info.get("ritmo_mensual", 0))
        }

    # DFS para encontrar todos los nodos alcanzables
    for sku in todos_skus_involucrados:
        visitados = set()
        alcanzables = set()
        
        def dfs(nodo):
            if nodo in visitados:
                return
            visitados.add(nodo)
            alcanzables.add(nodo)
            for hijo in grafo.get(nodo, set()):
                dfs(hijo)
                
        dfs(sku)
        
        # Armar la lista final y sumar
        familia_list = []
        stock_total = 0.0
        
        # Ordenamos los alcanzables para estabilidad en la visualización
        for nodo_alcanzable in sorted(list(alcanzables)):
            info_nodo = get_info(nodo_alcanzable)
            familia_list.append(info_nodo)
            stock_total += info_nodo["stock_act"]
            
        resultado[sku] = {
            "familia_maquila": familia_list,
            "stock_total_familia_maquila": stock_total
        }
        
    return resultado
