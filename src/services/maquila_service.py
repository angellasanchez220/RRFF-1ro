import re
import unicodedata

import pandas as pd
from sqlalchemy import text


FORMATOS_MAQUILA = ("CR", "PDQ", "MB")


def _normalizar_identificador(value):
    """Normaliza texto sin destruir los limites entre palabras/codigos."""
    if value is None or pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFD", str(value).strip().upper())
    return "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )


def _contiene_marcador(value, marcador):
    """Detecta CR/PDQ/MB sin confundirlos con letras dentro de una palabra.

    Se aceptan marcadores separados por espacios/guiones y tambien pegados a
    numeros en codigos internos (por ejemplo ``C9405CR`` o ``PDQ20``).
    """
    normalized = _normalizar_identificador(value)
    return bool(re.search(rf"(?<![A-Z]){re.escape(marcador)}(?![A-Z])", normalized))


def detectar_formato_producto(codigo_femaco, descripcion):
    """Clasifica un producto como LINEAL, CR, PDQ o MB."""
    marcadores = [
        marcador
        for marcador in FORMATOS_MAQUILA
        if _contiene_marcador(codigo_femaco, marcador)
        or _contiene_marcador(descripcion, marcador)
    ]
    if not marcadores:
        return "LINEAL"
    # Una descripcion/codigo con mas de un marcador queda trazable; el orden
    # solo entrega un valor estable para no romper la planificacion.
    return marcadores[0]


def is_discontinued(value):
    """Normaliza los estados que el planner trata como descontinuados."""
    if value is None:
        return False
    v = str(value).strip().upper()
    if not v:
        return False
    return v in {"DESCONTINUADO", "DESCONTINUADOS", "OBSOLETO", "INACTIVO", "INACTIVOS"}




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
            "formato_compra": detectar_formato_producto(
                codigo,
                row.get("nombre_producto"),
            ),
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
               r.producto_objetivo,
               c.id AS componente_id,
               c.sku_componente,
               COALESCE(c.cantidad_por_unidad, 1.0) AS cantidad_por_unidad,
               COALESCE(c.no_transformable, FALSE) as no_transformable,
               COALESCE(c.observacion, '') AS observacion
        FROM recetas_maquila r
        JOIN receta_maquila_componentes c ON c.receta_id = r.id
        WHERE r.activa = True AND r.sku_maquilable LIKE 'FAM-%'
          AND COALESCE(c.tipo_componente, 'PRODUCTO') = 'PRODUCTO'
    """), conn)
    
    # Construir grafo de adyacencia no dirigido
    grafo = {}
    todos_skus = set()
    no_transformable_map = {}
    familia_meta = {}
    componentes_por_familia = {}
    
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
                "producto_objetivo": str(row.get("producto_objetivo") or "").strip().upper(),
            }
            componentes_por_familia.setdefault(padre, []).append({
                "nodo": hijo,
                "cantidad_por_unidad": float(row.get("cantidad_por_unidad") or 1.0),
                "no_transformable": nt,
                "componente_id": int(row.get("componente_id") or 0),
                "observacion": str(row.get("observacion") or "").strip(),
            })
        
        if padre not in no_transformable_map:
            no_transformable_map[padre] = False
            
        if hijo not in no_transformable_map:
            no_transformable_map[hijo] = nt
        else:
            no_transformable_map[hijo] = no_transformable_map[hijo] or nt
            
    resultado = {}
    
    # sku_componente conserva su nombre histórico en la tabla, pero para las
    # familias FAM-* contiene el código interno (codigo_femaco).
    # Actualización: indexamos también por SKU para tolerar cuando 
    # la BD trae el SKU real en lugar del código interno.
    lookup_normalizado = {str(k).strip().upper(): v for k, v in lookup_dict.items()}
    for k, v in lookup_dict.items():
        sku_val = str(v.get("sku") or "").strip().upper()
        if sku_val and sku_val not in lookup_normalizado:
            # Guardamos el código interno original para usarlo más adelante
            v_copy = dict(v)
            v_copy["_codigo_femaco_orig"] = k
            lookup_normalizado[sku_val] = v_copy

    def get_info(codigo):
        info = lookup_normalizado.get(codigo, {})
        real_codigo = info.get("_codigo_femaco_orig", codigo)
        return {
            "codigo_femaco": real_codigo,
            "sku": str(info.get("sku") or "").strip(),
            "nombre_producto": info.get("nombre_producto", "Desconocido"),
            "stock_act": float(info.get("stock_act", 0)),
            "cantidad_transito": float(info.get("cantidad_transito", 0)),
            "ritmo_mensual": float(info.get("ritmo_mensual", 0)),
            "estado": str(info.get("estado") or "").strip().upper(),
            "descontinuado": is_discontinued(info.get("estado")),
            "no_transformable": no_transformable_map.get(codigo, False),
            "es_maquilable": bool(info.get("es_maquilable", False)),
            "formato_compra": info.get("formato_compra") or detectar_formato_producto(
                real_codigo,
                info.get("nombre_producto"),
            ),
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
        ritmo_reemplazable = 0.0
        
        for nodo_alcanzable in sorted(list(visitados)):
            if nodo_alcanzable.startswith("FAM-"):
                continue
                
            info = get_info(nodo_alcanzable)
            familia_list.append(info)
            if not info["descontinuado"]:
                stock_bruto += info["stock_act"]
                transito_bruto += info["cantidad_transito"]
            
            if nodo_alcanzable != codigo:
                if not info["no_transformable"] and not info["descontinuado"]:
                    reemplazos_validos.append(info)
                    stock_reemplazable += info["stock_act"]
                    transito_reemplazable += info["cantidad_transito"]
                    ritmo_reemplazable += info["ritmo_mensual"]

        familias_conectadas = [
            familia_meta[nodo]
            for nodo in sorted(visitados)
            if nodo in familia_meta
        ]
        nombres_familia = sorted({f["nombre"] for f in familias_conectadas})
        familia_ids = sorted({f["id"] for f in familias_conectadas})

        # Conversiones reales autorizadas por cada receta. La cantidad del
        # producto de origen indica cuantas unidades se consumen para obtener
        # una unidad del destino, tal como se registra en la BOM actual.
        conversiones = []
        ambiguedades_conversion = []
        for nodo_familia in sorted(visitados):
            componentes = componentes_por_familia.get(nodo_familia, [])
            if not componentes:
                continue
            meta = familia_meta[nodo_familia]
            for destino in componentes:
                destino_codigo = get_info(destino["nodo"])["codigo_femaco"]
                for origen in componentes:
                    if origen["nodo"] == destino["nodo"] or origen["no_transformable"]:
                        continue
                    origen_codigo = get_info(origen["nodo"])["codigo_femaco"]
                    conversiones.append({
                        "receta_id": meta["id"],
                        "nombre_receta": meta["nombre"],
                        "origen": str(origen_codigo).strip().upper(),
                        "destino": str(destino_codigo).strip().upper(),
                        "cantidad_origen": max(float(origen["cantidad_por_unidad"]), 0.0001),
                        "cantidad_destino": 1.0,
                        "prioridad": None,
                    })

        # Si dos recetas definen factores distintos para el mismo par, no se
        # elige uno silenciosamente: el simulador lo reportara como ambiguo.
        factores_por_par = {}
        for conversion in conversiones:
            par = (conversion["origen"], conversion["destino"])
            factores_por_par.setdefault(par, set()).add(
                (conversion["cantidad_origen"], conversion["cantidad_destino"])
            )
        for (origen, destino), factores in factores_por_par.items():
            if len(factores) > 1:
                ambiguedades_conversion.append(
                    f"Factores distintos para {origen} -> {destino}: {sorted(factores)}"
                )
        
        res_data = {
            "familia_skus": familia_list,
            "stock_bruto_familia": stock_bruto,
            "transito_bruto_familia": transito_bruto,
            "reemplazos_validos": reemplazos_validos,
            "stock_reemplazable_adicional": stock_reemplazable,
            "transito_reemplazable_adicional": transito_reemplazable,
            "ritmo_reemplazable_adicional": ritmo_reemplazable,
            "familia_ids": familia_ids,
            "nombres_familia": nombres_familia,
            "nombre_familia": " / ".join(nombres_familia),
            "cantidad_miembros": len(familia_list),
            "clave_familia": "FAM:" + ",".join(str(fid) for fid in familia_ids),
            "conversiones_autorizadas": conversiones,
            "ambiguedades_conversion": ambiguedades_conversion,
        }
        
        # Indexar tanto por el código de iteración como por el código interno real
        resultado[codigo] = res_data
        real_codigo = get_info(codigo)["codigo_femaco"]
        if real_codigo != codigo:
            resultado[real_codigo] = res_data
            
    return resultado

