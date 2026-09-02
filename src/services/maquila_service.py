import pandas as pd
from sqlalchemy import text

def build_maquila_families(conn, lookup_dict):
    """
    Construye las familias de reemplazo (simétricas) para todos los SKU
    involucrados en recetas de maquila activas.
    
    :param conn: Conexión a la BD (sqlalchemy).
    :param lookup_dict: Diccionario lookup de SKU a datos: 
           {"SKU1": {"nombre_producto": "X", "stock_act": 100, "ritmo_mensual": 50}, ...}
    :return: dict con el resultado por SKU.
             {"SKU1": {"familia_skus": [...], "stock_bruto_familia": 250, "reemplazos_validos": [...], "stock_reemplazable_adicional": 150}, ...}
    """
    df_comp = pd.read_sql(text("""
        SELECT r.id AS familia_id,
               r.sku_maquilable,
               COALESCE(NULLIF(TRIM(r.descripcion), ''), r.sku_maquilable) AS nombre_familia,
               c.sku_componente,
               COALESCE(c.no_transformable, FALSE) as no_transformable
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON c.receta_id = r.id
        WHERE r.activa = True AND r.sku_maquilable LIKE 'FAM-%'
    """), conn)
    
    # Construir grafo de adyacencia no dirigido
    grafo = {}
    todos_skus = set()
    no_transformable_map = {}
    familia_meta = {}
    
    for _, row in df_comp.iterrows():
        padre = str(row["sku_maquilable"]).strip()
        hijo = str(row["sku_componente"]).strip()
        nt = bool(row["no_transformable"])
        
        if not padre or not hijo: 
            continue
        
        if padre not in grafo: grafo[padre] = set()
        if hijo not in grafo: grafo[hijo] = set()
            
        grafo[padre].add(hijo)
        grafo[hijo].add(padre)
        
        todos_skus.add(padre)
        todos_skus.add(hijo)

        # Los nodos FAM-* son agrupadores internos. Guardamos sus datos para
        # poder exponer el nombre real de la familia en el dashboard.
        if padre.startswith("FAM-"):
            familia_meta[padre] = {
                "id": int(row["familia_id"]),
                "nombre": str(row["nombre_familia"]).strip(),
            }
        
        if padre not in no_transformable_map:
            no_transformable_map[padre] = False
            
        if hijo not in no_transformable_map:
            no_transformable_map[hijo] = nt
        else:
            no_transformable_map[hijo] = no_transformable_map[hijo] or nt
            
    resultado = {}
    
    # Evita que espacios accidentales en SKU impidan encontrar stock/nombre.
    lookup_normalizado = {str(k).strip(): v for k, v in lookup_dict.items()}

    def get_info(s):
        info = lookup_normalizado.get(s, {})
        return {
            "sku": s,
            "nombre_producto": info.get("nombre_producto", "Desconocido"),
            "stock_act": float(info.get("stock_act", 0)),
            "ritmo_mensual": float(info.get("ritmo_mensual", 0)),
            "no_transformable": no_transformable_map.get(s, False)
        }

    for sku in todos_skus:
        if sku.startswith("FAM-"):
            continue # Ignorar nodos dummy de agrupacion
            
        visitados = set()
        def dfs(nodo):
            if nodo in visitados: return
            visitados.add(nodo)
            for h in grafo.get(nodo, set()):
                dfs(h)
                
        dfs(sku)
        
        familia_list = []
        stock_bruto = 0.0
        
        reemplazos_validos = []
        stock_reemplazable = 0.0
        
        for nodo_alcanzable in sorted(list(visitados)):
            if nodo_alcanzable.startswith("FAM-"):
                continue
                
            info = get_info(nodo_alcanzable)
            familia_list.append(info)
            stock_bruto += info["stock_act"]
            
            if nodo_alcanzable != sku:
                if not info["no_transformable"]:
                    reemplazos_validos.append(info)
                    stock_reemplazable += info["stock_act"]

        familias_conectadas = [
            familia_meta[nodo]
            for nodo in sorted(visitados)
            if nodo in familia_meta
        ]
        nombres_familia = sorted({f["nombre"] for f in familias_conectadas})
        familia_ids = sorted({f["id"] for f in familias_conectadas})
            
        resultado[sku] = {
            "familia_skus": familia_list,
            "stock_bruto_familia": stock_bruto,
            "reemplazos_validos": reemplazos_validos,
            "stock_reemplazable_adicional": stock_reemplazable,
            "familia_ids": familia_ids,
            "nombres_familia": nombres_familia,
            "nombre_familia": " / ".join(nombres_familia),
            "cantidad_miembros": len(familia_list),
        }
        
    return resultado
