"""Reglas puras para determinar el stock usado por la sugerencia de compra."""

import pandas as pd


def aplicar_stock_familia_para_sugerencia(
    df: pd.DataFrame,
    familias_map: dict,
) -> pd.DataFrame:
    """Reemplaza el stock de cálculo por el total familiar cuando corresponde.

    ``stock_act`` se mantiene intacto como inventario individual. La columna
    ``sug_stock_actual`` es la que consume el cálculo de sugerencia de compra.
    """
    resultado = df.copy()
    stock_individual = pd.to_numeric(
        resultado.get("stock_act", pd.Series(0, index=resultado.index)),
        errors="coerce",
    ).fillna(0.0)

    transito_individual = pd.to_numeric(
        resultado.get("cantidad_transito", pd.Series(0, index=resultado.index)),
        errors="coerce",
    ).fillna(0.0)

    stocks_familia = []
    transitos_familia = []
    usa_familia = []
    cantidades_miembros = []
    nombres_familia = []

    identificadores = resultado.get("codigo_femaco", resultado["sku"])

    for codigo_femaco, stock_sku, transito_sku in zip(
        identificadores.fillna("").astype(str).str.strip().str.upper(),
        stock_individual,
        transito_individual,
    ):
        familia = familias_map.get(codigo_femaco, {})
        miembros = familia.get("familia_skus") or []
        es_familia_activa = len(miembros) > 1

        if es_familia_activa:
            try:
                stock_reemplazable = float(familia.get("stock_reemplazable_adicional", 0))
                stock_calculo = float(stock_sku) + stock_reemplazable
                
                transito_reemplazable = float(familia.get("transito_reemplazable_adicional", 0))
                transito_calculo = float(transito_sku) + transito_reemplazable
            except (TypeError, ValueError):
                stock_calculo = float(stock_sku)
                transito_calculo = float(transito_sku)
        else:
            stock_calculo = float(stock_sku)
            transito_calculo = float(transito_sku)

        stocks_familia.append(stock_calculo)
        transitos_familia.append(transito_calculo)
        usa_familia.append(es_familia_activa)
        cantidades_miembros.append(len(miembros) if es_familia_activa else 1)
        nombres_familia.append(familia.get("nombre_familia", "") if es_familia_activa else "")

    resultado["sug_stock_individual"] = stock_individual
    resultado["sug_stock_familia"] = stocks_familia
    resultado["sug_stock_actual"] = stocks_familia
    resultado["sug_transito_actual"] = transitos_familia
    resultado["sug_usa_stock_familia"] = usa_familia
    resultado["sug_cantidad_miembros_familia"] = cantidades_miembros
    resultado["sug_nombre_familia"] = nombres_familia
    return resultado
