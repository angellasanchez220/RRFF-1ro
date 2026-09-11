import pandas as pd
from sqlalchemy import text


def is_discontinued(value):
    """Normaliza los estados que el planner trata como descontinuados."""
    if pd.isna(value) or not value:
        return False
    return str(value).strip().upper() in {"DESCONTINUADO", "DESCONTINUADOS", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"}


def build_product_lookup_by_internal_code(df, ritmo_col="ritmo_mensual"):
    """Construye un lookup estable por CÓD. interno.

    Los códigos vacíos no representan productos identificables y se omiten.
    Si el origen trae un código repetido, se conserva una sola entrada para
    evitar contar dos veces el mismo producto y para no depender de un índice
    único de pandas.
    """
    if df.empty or "codigo_femaco" not in df.columns:
        return {}

    lookup = {}
    for _, row in df.iterrows():
        codigo_value = row.get("codigo_femaco")
        if pd.isna(codigo_value):
            continue

        codigo = str(codigo_value).strip().upper()
        if not codigo or codigo in lookup:
            continue

        stock_value = row.get("stock_act", 0)
        transito_value = row.get("cantidad_transito", 0)
        ritmo_value = row.get(ritmo_col, 0)
        estado_value = row.get("estado")
        lookup[codigo] = {
            "sku": "" if pd.isna(row.get("sku")) else str(row.get("sku")).strip(),
            "nombre_producto": (
                "Desconocido"
                if pd.isna(row.get("nombre_producto"))
                else str(row.get("nombre_producto")).strip()
            ),
            "stock_act": 0 if pd.isna(stock_value) else stock_value,
            "cantidad_transito": 0 if pd.isna(transito_value) else transito_value,
            "ritmo_mensual": 0 if pd.isna(ritmo_value) else ritmo_value,
            "estado": "" if pd.isna(estado_value) else str(estado_value).strip().upper(),
        }

    return lookup


def build_maquila_families(conn, lookup_dict):
    """
    Construye las familias de reemplazo (simétricas) para todos los códigos
    internos (codigo_femaco)
    involucrados en recetas de maquila activas.
    
    :param conn: Conexión a la BD (sqlalchemy).
    :param lookup_dict: Diccionario indexado por código interno:
           {"COD1": {"sku": "SKU1", "nombre_producto": "X", ...}, ...}
    :return: dict con el resultado por código interno.
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
        padre = str(row["sku_maquilable"]).strip().upper()
        hijo = str(row["sku_componente"]).strip().upper()
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
    
    # sku_componente conserva su nombre histórico en la tabla, pero para las
    # familias FAM-* contiene el código interno (codigo_femaco).
    lookup_normalizado = {str(k).strip().upper(): v for k, v in lookup_dict.items()}

    def get_info(codigo):
        info = lookup_normalizado.get(codigo, {})
        return {
            "codigo_femaco": codigo,
            "sku": str(info.get("sku") or "").strip(),
            "nombre_producto": info.get("nombre_producto", "Desconocido"),
            "stock_act": float(info.get("stock_act", 0)),
            "cantidad_transito": float(info.get("cantidad_transito", 0)),
            "ritmo_mensual": float(info.get("ritmo_mensual", 0)),
            "estado": str(info.get("estado") or "").strip().upper(),
            "descontinuado": is_discontinued(info.get("estado")),
            "no_transformable": no_transformable_map.get(codigo, False)
        }

    for codigo in todos_skus:
        if codigo.startswith("FAM-"):
            continue # Ignorar nodos dummy de agrupacion
            
        visitados = set()
        def dfs(nodo):
            if nodo in visitados: return
            visitados.add(nodo)
            for h in grafo.get(nodo, set()):
                dfs(h)
                
        dfs(codigo)
        
        familia_list = []
        stock_bruto = 0.0
        transito_bruto = 0.0
        
        reemplazos_validos = []
        stock_reemplazable = 0.0
        transito_reemplazable = 0.0
        
        for nodo_alcanzable in sorted(list(visitados)):
            if nodo_alcanzable.startswith("FAM-"):
                continue
                
            info = get_info(nodo_alcanzable)
            familia_list.append(info)
            # Ya no ignoramos el stock de los descontinuados, sí se puede usar para cubrir necesidades de la familia
            stock_bruto += info["stock_act"]
            transito_bruto += info["cantidad_transito"]
            
            if nodo_alcanzable != codigo:
                if not info["no_transformable"]:
                    reemplazos_validos.append(info)
                    stock_reemplazable += info["stock_act"]
                    transito_reemplazable += info["cantidad_transito"]

        familias_conectadas = [
            familia_meta[nodo]
            for nodo in sorted(visitados)
            if nodo in familia_meta
        ]
        nombres_familia = sorted({f["nombre"] for f in familias_conectadas})
        familia_ids = sorted({f["id"] for f in familias_conectadas})
            
        resultado[codigo] = {
            "familia_skus": familia_list,
            "stock_bruto_familia": stock_bruto,
            "transito_bruto_familia": transito_bruto,
            "reemplazos_validos": reemplazos_validos,
            "stock_reemplazable_adicional": stock_reemplazable,
            "transito_reemplazable_adicional": transito_reemplazable,
            "familia_ids": familia_ids,
            "nombres_familia": nombres_familia,
            "nombre_familia": " / ".join(nombres_familia),
            "cantidad_miembros": len(familia_list),
        }
        
    return resultado
