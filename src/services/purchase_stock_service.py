"""Simulacion pura de compra proyectada y consumo compartido de maquila."""

from __future__ import annotations

import json
import math

import pandas as pd

try:
    from src.services.maquila_service import detectar_formato_producto
except ModuleNotFoundError:
    from services.maquila_service import detectar_formato_producto


MESES_ESPERA_CONTENEDOR = 4
FORMATOS_DONANTES_LINEAL = {"CR", "PDQ", "MB"}


def _numero(value, default=0.0):
    try:
        number = float(value)
        return default if math.isnan(number) else number
    except (TypeError, ValueError):
        return default


def _ceil_to_multiple(value, multiple):
    value = max(_numero(value), 0.0)
    multiple = _numero(multiple)
    if multiple <= 0:
        return value
    return math.ceil(value / multiple) * multiple


def _identificador(row):
    codigo = str(row.get("codigo_femaco") or "").strip().upper()
    sku = str(row.get("sku") or "").strip().upper()
    return codigo or sku


def _familia_para_fila(row, familias_map):
    codigo = str(row.get("codigo_femaco") or "").strip().upper()
    sku = str(row.get("sku") or "").strip().upper()
    return familias_map.get(codigo) or familias_map.get(sku) or {}


def _clave_familia(row, familia):
    miembros = familia.get("familia_skus") or []
    if len(miembros) <= 1:
        return f"SKU:{_identificador(row)}"
    clave = str(familia.get("clave_familia") or "").strip()
    if clave:
        return clave
    ids = familia.get("familia_ids") or []
    if ids:
        return "FAM:" + ",".join(str(value) for value in sorted(ids))
    codigos = sorted(
        str(member.get("codigo_femaco") or member.get("sku") or "").strip().upper()
        for member in miembros
    )
    return "FAM-CODES:" + ",".join(codigos)


def _transitos_mensuales(row, meses_espera):
    buckets = []
    has_buckets = any(
        f"transito_mes_{month}" in row.index
        for month in range(1, meses_espera + 1)
    )
    if has_buckets:
        for month in range(1, meses_espera + 1):
            buckets.append(max(_numero(row.get(f"transito_mes_{month}")), 0.0))
        return buckets

    confirmed = max(_numero(row.get("cantidad_transito_confirmado_4m")), 0.0)
    return [0.0] * (meses_espera - 1) + [confirmed]


def _resolver_conversiones(candidates, states, identifier_to_position):
    """Devuelve reglas utilizables o una ambiguedad sin imponer prioridad."""
    by_source = {}
    ambiguities = []
    for conversion in candidates:
        source = str(conversion.get("origen") or "").strip().upper()
        source_position = identifier_to_position.get(source)
        if source_position is None:
            continue
        source_state = states[source_position]
        if source_state["formato"] not in FORMATOS_DONANTES_LINEAL:
            continue
        origin_qty = max(_numero(conversion.get("cantidad_origen"), 1.0), 0.0001)
        destination_qty = max(_numero(conversion.get("cantidad_destino"), 1.0), 0.0001)
        if source_state["stock"] + 1e-9 < origin_qty:
            continue
        by_source.setdefault(source, []).append({
            **conversion,
            "cantidad_origen": origin_qty,
            "cantidad_destino": destination_qty,
            "source_position": source_position,
        })

    usable = []
    for source, rules in by_source.items():
        ratios = {
            (rule["cantidad_origen"], rule["cantidad_destino"])
            for rule in rules
        }
        if len(ratios) > 1:
            ambiguities.append(
                f"Factores distintos para transformar {source}: {sorted(ratios)}"
            )
            continue
        usable.append(rules[0])

    if len(usable) <= 1:
        return usable, ambiguities

    priorities = [rule.get("prioridad") for rule in usable]
    if all(priority is not None for priority in priorities):
        return sorted(
            usable,
            key=lambda rule: (rule["prioridad"], rule["origen"]),
        ), ambiguities

    ambiguities.append(
        "Multiples origenes con stock y sin prioridad de maquila: "
        + ", ".join(sorted(rule["origen"] for rule in usable))
    )
    return [], ambiguities


def calcular_compra_proyectada(
    df: pd.DataFrame,
    familias_map: dict,
    meses_espera: int = MESES_ESPERA_CONTENEDOR,
) -> pd.DataFrame:
    """Simula espera, ventas, transitos y maquila sin mutar inventario real.

    La demanda mensual es la venta de las ultimas cuatro semanas cerradas. Se
    consumen primero las ventas propias de todos los formatos y solo despues
    se permite que CR/PDQ/MB cubran un deficit LINEAL mediante una receta real.
    """
    if df.empty:
        return df.copy()

    result = df.copy().reset_index(drop=False).rename(
        columns={"index": "_original_index"}
    )
    states = {}
    identifier_to_position = {}
    family_groups = {}
    family_by_position = {}

    for position, row in result.iterrows():
        identifier = _identificador(row)
        sku_identifier = str(row.get("sku") or "").strip().upper()
        family = _familia_para_fila(row, familias_map)
        family_key = _clave_familia(row, family)
        family_by_position[position] = family
        family_groups.setdefault(family_key, []).append(position)

        format_name = detectar_formato_producto(
            row.get("codigo_femaco"),
            row.get("nombre_producto"),
        )
        states[position] = {
            "identifier": identifier,
            "sku": str(row.get("sku") or "").strip(),
            "formato": format_name,
            "family_key": family_key,
            "stock_inicial": max(_numero(row.get("stock_act")), 0.0),
            "stock": max(_numero(row.get("stock_act")), 0.0),
            "demanda_mensual": max(
                _numero(row.get("total_4_sem_verificado")),
                0.0,
            ),
            "transitos": _transitos_mensuales(row, meses_espera),
            "deficit": 0.0,
            "maquila_recibida": 0.0,
            "maquila_destinada": 0.0,
            "eventos": [],
            "ambiguedades": list(family.get("ambiguedades_conversion") or []),
        }
        if identifier:
            identifier_to_position[identifier] = position
        if sku_identifier:
            identifier_to_position[sku_identifier] = position

    for month in range(1, meses_espera + 1):
        monthly_shortages = {}

        for position, state in states.items():
            state["stock"] += state["transitos"][month - 1]
            own_demand = state["demanda_mensual"]
            own_fulfilled = min(state["stock"], own_demand)
            state["stock"] -= own_fulfilled
            monthly_shortages[position] = max(own_demand - own_fulfilled, 0.0)

        for positions in family_groups.values():
            for target_position in positions:
                target = states[target_position]
                shortage = monthly_shortages[target_position]
                if target["formato"] != "LINEAL" or shortage <= 1e-9:
                    continue

                family = family_by_position[target_position]
                target_identifier = target["identifier"]
                candidates = [
                    conversion
                    for conversion in family.get("conversiones_autorizadas") or []
                    if str(conversion.get("destino") or "").strip().upper()
                    == target_identifier
                ]
                usable, ambiguities = _resolver_conversiones(
                    candidates,
                    states,
                    identifier_to_position,
                )
                target["ambiguedades"].extend(ambiguities)

                for conversion in usable:
                    if shortage <= 1e-9:
                        break
                    source_position = conversion["source_position"]
                    source = states[source_position]
                    origin_qty = conversion["cantidad_origen"]
                    destination_qty = conversion["cantidad_destino"]
                    max_batches = math.floor((source["stock"] + 1e-9) / origin_qty)
                    needed_batches = math.ceil(shortage / destination_qty)
                    batches = min(max_batches, needed_batches)
                    if batches <= 0:
                        continue

                    consumed = batches * origin_qty
                    produced = batches * destination_qty
                    used_for_shortage = min(produced, shortage)
                    source["stock"] = max(source["stock"] - consumed, 0.0)
                    source["maquila_destinada"] += consumed
                    target["stock"] += max(produced - used_for_shortage, 0.0)
                    target["maquila_recibida"] += produced
                    shortage -= used_for_shortage
                    event = {
                        "mes": month,
                        "origen": source["identifier"],
                        "destino": target_identifier,
                        "unidades_origen": consumed,
                        "unidades_destino": used_for_shortage,
                        "receta_id": conversion.get("receta_id"),
                    }
                    source["eventos"].append(event)
                    target["eventos"].append(event)

                monthly_shortages[target_position] = max(shortage, 0.0)

        for position, shortage in monthly_shortages.items():
            states[position]["deficit"] += max(shortage, 0.0)

    for position, state in states.items():
        row = result.loc[position]
        coverage_months = max(
            _numero(row.get("meses_cobertura_objetivo"), 5.4),
            0.0,
        )
        target_stock = round(state["demanda_mensual"] * coverage_months, 0)
        gross_purchase = max(target_stock - state["stock"], 0.0)
        final_purchase = _ceil_to_multiple(gross_purchase, row.get("ump"))
        family = family_by_position[position]
        family_positions = family_groups[state["family_key"]]
        family_stock = sum(states[p]["stock_inicial"] for p in family_positions)
        confirmed_transit = sum(state["transitos"])

        result.at[position, "formato_compra"] = state["formato"]
        result.at[position, "clave_familia_compra"] = state["family_key"]
        result.at[position, "sug_nombre_familia"] = family.get("nombre_familia", "")
        result.at[position, "sug_usa_stock_familia"] = state["maquila_recibida"] > 0
        result.at[position, "sug_cantidad_miembros_familia"] = len(family_positions)
        result.at[position, "sug_stock_individual"] = state["stock_inicial"]
        result.at[position, "sug_stock_familia"] = family_stock
        result.at[position, "sug_stock_actual"] = state["stock_inicial"]
        result.at[position, "sug_transito_actual"] = confirmed_transit
        result.at[position, "sug_cantidad_transito"] = confirmed_transit
        result.at[position, "demanda_espera_4_meses"] = (
            state["demanda_mensual"] * meses_espera
        )
        result.at[position, "maquila_recibida_4_meses"] = state["maquila_recibida"]
        result.at[position, "maquila_destinada_4_meses"] = state["maquila_destinada"]
        result.at[position, "stock_estimado_llegada"] = max(state["stock"], 0.0)
        result.at[position, "deficit_espera_4_meses"] = state["deficit"]
        result.at[position, "sug_target_meses"] = coverage_months
        result.at[position, "sug_target_uds"] = target_stock
        result.at[position, "stock_objetivo"] = target_stock
        result.at[position, "sugerencia_bruta"] = gross_purchase
        result.at[position, "sugerencia_compra_inmediata_uds"] = final_purchase
        result.at[position, "sugerencia_final"] = final_purchase
        result.at[position, "ambiguedad_maquila"] = " | ".join(
            dict.fromkeys(state["ambiguedades"])
        )
        result.at[position, "detalle_maquila_proyectada"] = json.dumps(
            state["eventos"],
            ensure_ascii=False,
        )

    for family_key, positions in family_groups.items():
        summary_items = []
        family_total = 0.0
        for position in positions:
            row = result.loc[position]
            purchase = _numero(row.get("sugerencia_final"))
            family_total += purchase
            summary_items.append({
                "sku": str(row.get("sku") or "").strip(),
                "codigo_femaco": str(row.get("codigo_femaco") or "").strip(),
                "formato": row.get("formato_compra"),
                "compra_sugerida": purchase,
            })
        summary = json.dumps(
            {
                "familia": family_key,
                "formatos": summary_items,
                "total": family_total,
            },
            ensure_ascii=False,
        )
        for position in positions:
            result.at[position, "familia_compra_total"] = family_total
            result.at[position, "familia_resumen_compras"] = summary

    original_index = result.pop("_original_index")
    result.index = original_index
    result.index.name = df.index.name
    return result


def recalcular_resumen_familias(df: pd.DataFrame) -> pd.DataFrame:
    """Sincroniza los totales familiares con la sugerencia final vigente."""
    if df.empty or "clave_familia_compra" not in df.columns:
        return df

    result = df.copy()
    for family_key, indexes in result.groupby("clave_familia_compra").groups.items():
        summary_items = []
        family_total = 0.0
        for index in indexes:
            row = result.loc[index]
            purchase = _numero(row.get("sugerencia_final"))
            family_total += purchase
            summary_items.append({
                "sku": str(row.get("sku") or "").strip(),
                "codigo_femaco": str(row.get("codigo_femaco") or "").strip(),
                "formato": row.get("formato_compra"),
                "compra_sugerida": purchase,
            })
        summary = json.dumps(
            {
                "familia": family_key,
                "formatos": summary_items,
                "total": family_total,
            },
            ensure_ascii=False,
        )
        result.loc[indexes, "familia_compra_total"] = family_total
        result.loc[indexes, "familia_resumen_compras"] = summary
    return result


def aplicar_stock_familia_para_sugerencia(
    df: pd.DataFrame,
    familias_map: dict,
) -> pd.DataFrame:
    """Compatibilidad: aplica el nuevo modelo sin consolidar stock por SKU."""
    return calcular_compra_proyectada(df, familias_map)

