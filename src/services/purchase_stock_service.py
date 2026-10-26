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
    ritmos_familia_adicional = []
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
        
        # Check if the current product is marked as non-transformable
        current_info = next((m for m in miembros if str(m.get("codigo_femaco", "")).upper() == codigo_femaco or str(m.get("sku", "")).upper() == codigo_femaco), {})
        no_transformable = current_info.get("no_transformable", False)
        
        # If it is no_transformable, it behaves independently and doesn't use the family stock
        es_familia_activa = len(miembros) > 1 and not no_transformable

        if es_familia_activa:
            try:
                if "stock_bruto_familia" in familia:
                    stock_calculo = float(familia["stock_bruto_familia"])
                else:
                    stock_reemplazable = float(familia.get("stock_reemplazable_adicional", 0))
                    stock_calculo = float(stock_sku) + stock_reemplazable
                
                if "transito_bruto_familia" in familia:
                    transito_calculo = float(familia["transito_bruto_familia"])
                else:
                    transito_reemplazable = float(familia.get("transito_reemplazable_adicional", 0))
                    transito_calculo = float(transito_sku) + transito_reemplazable
                
                ritmo_reemplazable = float(familia.get("ritmo_reemplazable_adicional", 0))
            except (TypeError, ValueError):
                stock_calculo = float(stock_sku)
                transito_calculo = float(transito_sku)
                ritmo_reemplazable = 0.0
        else:
            stock_calculo = float(stock_sku)
            transito_calculo = float(transito_sku)
            ritmo_reemplazable = 0.0

        stocks_familia.append(stock_calculo)
        transitos_familia.append(transito_calculo)
        ritmos_familia_adicional.append(ritmo_reemplazable)
        usa_familia.append(es_familia_activa)
        cantidades_miembros.append(len(miembros) if es_familia_activa else 1)
        nombres_familia.append(familia.get("nombre_familia", "") if es_familia_activa else "")

    resultado["sug_stock_individual"] = stock_individual
    resultado["sug_stock_familia"] = stocks_familia
    resultado["sug_stock_actual"] = [sf if uf else si for sf, uf, si in zip(stocks_familia, usa_familia, stock_individual)]
    resultado["sug_transito_actual"] = [tf if uf else ti for tf, uf, ti in zip(transitos_familia, usa_familia, transito_individual)]
    resultado["sug_ritmo_reemplazable_adicional_4_sem"] = 0.0
    resultado["sug_usa_stock_familia"] = usa_familia
    resultado["sug_cantidad_miembros_familia"] = cantidades_miembros
    resultado["sug_nombre_familia"] = nombres_familia
    return resultado

