"""
api/routes/sop.py — v2.4
=========================
LÓGICA CORRECTA:
- Calendario: SIEMPRE Enero→Diciembre (año fijo).
  * Ene-Abr 2026 = datos reales 2026 (si existen en la DB)
  * May-Dic 2026  = proyección 2025 base (columnas sellout_may_2026…sellout_dic_2026)
  * NO usar 2027
- Semanas: leer de fact_ventas, excluir la semana actual (incompleta).
  sem1 = semana más reciente COMPLETADA
  sem2, sem3, sem4 = semanas anteriores
- Alertas: basadas en stock_act (Femaco), NO stock HC
- Objetivo = (sellout_mes_anterior_estimado + total_4_sem) / 2
- Observaciones: fix del body parsing (usar Body(...))
"""
import math
import re
from datetime import date, timedelta
from fastapi import APIRouter, Header, HTTPException, Body
from sqlalchemy import text
import pandas as pd

from api.db import engine
from api.routes.auth import decode_token, _get_auth_header

router = APIRouter()

# Calendario fijo: Enero a Diciembre
MESES = [
    (1,  "Enero",      "ene"),
    (2,  "Febrero",    "feb"),
    (3,  "Marzo",      "mar"),
    (4,  "Abril",      "abr"),
    (5,  "Mayo",       "may"),
    (6,  "Junio",      "jun"),
    (7,  "Julio",      "jul"),
    (8,  "Agosto",     "ago"),
    (9,  "Septiembre", "sep"),
    (10, "Octubre",    "oct"),
    (11, "Noviembre",  "nov"),
    (12, "Diciembre",  "dic"),
]


def _safe(v, default=0):
    if v is None:
        return default
    try:
        if isinstance(v, float) and math.isnan(v):
            return default
        return int(round(float(v)))
    except Exception:
        return default


"""
MAPEO REAL DE COLUMNAS EN LA DB:
  sellout_may_2026 .. sellout_dic_2026  →  datos reales Mayo-Dic 2025
  sellout_ene_2027 .. sellout_abr_2027  →  datos reales Ene-Abr 2026
  (el planner los nombró con el año siguiente como "proyección base")

TABLA FIJA Enero→Diciembre:
  Ene-Abr (pasados en 2026): columnas _2027 → mostrar como "Ene 2026".."Abr 2026"
  May-Dic (no cerrados 2026): columnas _2026 → mostrar como "May 2025".."Dic 2025"
  Mayo 2026 actual (aún no cerrado): usa columna may_2026 = dato real Mayo 2025

GRÁFICO: 12 meses cronológicos más recientes, sin proyecciones.
  May 2025 → Jun 2025 → … → Dic 2025 → Ene 2026 → … → Abr 2026
"""

# Mapeo: mes_num → (abrev_db, año_db, label_display, año_display)
# Para hoy = Mayo 2026: Ene-Abr usan _2027 (dato real 2026), May-Dic usan _2026 (dato real 2025)
def _get_mes_map():
    """Devuelve lista de 12 entradas: (mes_num, nombre, abrev_db, año_db, año_label)."""
    today = date.today()
    mes_actual = today.month   # 5
    yr = today.year            # 2026

    result = []
    for mes_num, nombre, abrev in MESES:
        # Meses ya cerrados este año → col _2027, label yr
        if mes_num < mes_actual:
            result.append((mes_num, nombre, abrev, yr + 1, yr))
        # Mes actual + futuros → col _2026, label yr-1
        else:
            result.append((mes_num, nombre, abrev, yr, yr - 1))
    return result


def _build_month_calendar(cols: list, row: dict) -> list:
    """
    Tabla FIJA Enero→Diciembre.
    Ene-Abr 2026 reales → columnas _2027.
    May-Dic 2025 reales → columnas _2026.
    Sin proyecciones.
    """
    mes_map = _get_mes_map()
    result = []
    for mes_num, nombre, abrev, yr_db, yr_label in mes_map:
        col_so = f"sellout_{abrev}_{yr_db}"
        col_si = f"sellin_{abrev}_{yr_db}"
        so_val = _safe(row.get(col_so)) if col_so in cols else 0
        si_val = _safe(row.get(col_si)) if col_si in cols else 0
        result.append({
            "mes":       nombre,
            "label":     f"{nombre} {yr_label}",
            "mes_num":   mes_num,
            "yr_label":  yr_label,
            "sell_out":  so_val,
            "sell_in":   si_val,
        })
    return result


def _build_chart_12m(cols: list, row: dict) -> list:
    """
    Gráfico continuo de 12 meses de historia.
    Orden cronológico.
    """
    mes_map = _get_mes_map()
    today = date.today()
    mes_actual = today.month
    pasados  = [m for m in mes_map if m[0] < mes_actual]   # Ene-Abr 2026
    recientes = [m for m in mes_map if m[0] >= mes_actual]  # May-Dic 2025

    chart = []
    historial = recientes + pasados

    # HISTORIA (12 meses)
    prev_so = None
    for mes_num, nombre, abrev, yr_db, yr_label in historial:
        col_so = f"sellout_{abrev}_{yr_db}"
        col_si = f"sellin_{abrev}_{yr_db}"
        so_val = _safe(row.get(col_so)) if col_so in cols else 0
        si_val = _safe(row.get(col_si)) if col_si in cols else 0

        # Crecimiento MoM
        growth = None
        if prev_so is not None and prev_so > 0:
            growth = round(((so_val - prev_so) / prev_so) * 100, 1)

        chart.append({
            "name": f"{nombre[:3]} {yr_label}",
            "Sell Out": so_val,
            "Sell In": si_val,
            "growth_pct": growth
        })
        prev_so = so_val

    return chart




# Mes abreviado → número
_MON = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
        'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
        'ene':1,'abr':4,'ago':8,'dic':12}

def _col_sort_key(col: str) -> tuple:
    """Ordena columnas unidades{DD}_{mon}... cronológicamente por fecha inicio."""
    m = re.search(r'unidades(\d+)_([a-z]+)', col)
    if m:
        return (_MON.get(m.group(2), 0), int(m.group(1)))
    return (99, 99)


def _get_semanas_fact_ventas(conn) -> dict:
    """
    Lee fact_ventas. Ordena columnas CRONOLÓGICAMENTE (no alfabéticamente).
    sem1 = semana más reciente COMPLETA, sem2, sem3, sem4 = anteriores en orden.
    Excluye la semana actual si está incompleta (0 o < 20% del promedio).
    """
    try:
        df = pd.read_sql(text("SELECT * FROM fact_ventas"), conn)
    except Exception:
        return {}
    if df.empty:
        return {}

    df["sku"] = df["sku"].astype(str).str.strip()

    # Ordenar columnas CRONOLÓGICAMENTE por fecha de inicio de semana
    sem_cols = sorted(
        [c for c in df.columns if c.startswith("unidades")
         and c not in ("unidades_semana_actual",)],
        key=_col_sort_key
    )
    if len(sem_cols) < 2:
        return {}

    result = {}
    for _, row in df.iterrows():
        sku = row["sku"]
        vals = []
        for c in sem_cols:
            v = pd.to_numeric(row.get(c), errors="coerce")
            vals.append(0 if pd.isna(v) else int(v))

        # vals ahora en orden cronológico: [oldest, ..., newest]
        semana_excluida = False
        fecha_ultima = sem_cols[-1] if sem_cols else "N/A"
        
        # Descartar la última columna si es semana actual incompleta
        if len(vals) >= 2:
            avg_prev = sum(vals[:-1]) / max(len(vals) - 1, 1) if sum(vals[:-1]) > 0 else 1
            if vals[-1] == 0 or vals[-1] < avg_prev * 0.25:
                completed = vals[:-1]   # descartar semana incompleta
                semana_excluida = True
                fecha_ultima = sem_cols[-2] if len(sem_cols) >= 2 else sem_cols[0]
            else:
                completed = vals
        else:
            completed = vals

        # Las 4 semanas más recientes (completed ya es oldest→newest = [125,128,94,154])
        recent4 = completed[-4:] if len(completed) >= 4 else completed
        
        sem1 = recent4[0] if len(recent4) >= 1 else 0
        sem2 = recent4[1] if len(recent4) >= 2 else 0
        sem3 = recent4[2] if len(recent4) >= 3 else 0
        sem4 = recent4[3] if len(recent4) >= 4 else 0
        
        total_validas = sum(recent4)
        cantidad_validas = len(recent4) if len(recent4) > 0 else 1
        ritmo_semanal = total_validas / cantidad_validas
        ritmo_mensual = ritmo_semanal * 4.33

        result[sku] = {
            "sem1_uds": sem1,
            "sem2_uds": sem2,
            "sem3_uds": sem3,
            "sem4_uds": sem4,
            "total_4_sem_verificado": total_validas,
            "cantidad_semanas_validas": cantidad_validas,
            "semana_excluida_por_incompleta": semana_excluida,
            "fecha_ultima_semana_valida": fecha_ultima,
            "ritmo_semanal_verificado": ritmo_semanal,
            "ritmo_mensual_verificado": ritmo_mensual,
            "stock_fisico_matrix": _safe(row.get("stock_fsico")),
        }
    return result


# ── GET /api/sop/ ─────────────────────────────────────────────────────────────
@router.get("/")
def get_sop():
    """Retorna todos los SKUs con métricas completas para el dashboard React."""
    with engine.connect() as conn:
        try:
            df_sop = pd.read_sql(text("SELECT * FROM planificacion_sop ORDER BY sku"), conn)
        except Exception:
            return []  # Base de datos vacia

        # Semanas correctas desde fact_ventas
        try:
            sem_map = _get_semanas_fact_ventas(conn)
        except Exception:
            sem_map = {}

        # Tránsito activo
        try:
            df_tr = pd.read_sql(text("""
                SELECT sku,
                       SUM(cantidad) AS cantidad_transito,
                       MIN(COALESCE(eta_ajustada, fecha_disponibilidad_real)) AS eta_proxima
                FROM control_embarques
                WHERE estado IN ('EN_TRANSITO','EN_AFORO','RETRASADO')
                GROUP BY sku
            """), conn)
        except Exception:
            df_tr = pd.DataFrame(columns=["sku", "cantidad_transito", "eta_proxima"])

        # Observaciones
        try:
            df_obs = pd.read_sql(
                text("SELECT sku, observacion, usuario AS obs_usuario, "
                     "fecha_modificacion AS obs_fecha FROM sku_observaciones"),
                conn
            )
        except Exception:
            df_obs = pd.DataFrame(columns=["sku", "observacion", "obs_usuario", "obs_fecha"])

        # Maquila activa
        try:
            df_maq = pd.read_sql(text("""
                SELECT r.sku_maquilable AS sku, 
                       True AS es_maquilable,
                       r.id AS receta_maquila_id,
                       (SELECT COUNT(*) FROM receta_maquila_componentes c WHERE c.receta_id = r.id) as cantidad_componentes_receta
                FROM recetas_maquila r 
                WHERE r.activa = True
            """), conn)
        except Exception:
            df_maq = pd.DataFrame(columns=["sku", "es_maquilable", "receta_maquila_id", "cantidad_componentes_receta"])

    # Merge principal
    df = df_sop.copy()
    if "cantidad_transito" in df.columns:
        df = df.drop(columns=["cantidad_transito"]) # Evita collision _x _y con df_tr
        
    df["sku"] = df["sku"].astype(str)
    for d in (df_tr, df_obs, df_maq):
        if not d.empty:
            d["sku"] = d["sku"].astype(str)
    df = df.merge(df_tr,  on="sku", how="left")
    df = df.merge(df_obs, on="sku", how="left")
    df = df.merge(df_maq, on="sku", how="left")
    df["es_maquilable"] = df["es_maquilable"].fillna(False)

    # Aplicar semanas correctas desde fact_ventas
    for col in ("sem1_uds", "sem2_uds", "sem3_uds", "sem4_uds",
                "total_4_sem_verificado", "stock_fisico_matrix",
                "cantidad_semanas_validas", "semana_excluida_por_incompleta",
                "fecha_ultima_semana_valida", "ritmo_semanal_verificado",
                "ritmo_mensual_verificado"):
        df[col] = df["sku"].map(lambda s: sem_map.get(s, {}).get(col, 0 if "fecha" not in col else "N/A"))

    # Numéricos
    for col in ("stock_act", "cantidad_transito", "ump",
                "ritmo_semanal_uds", "sem1_uds", "sem2_uds",
                "sem3_uds", "sem4_uds", "total_4_sem_verificado",
                "stock_fisico_matrix", "sellout_mes_anterior_estimado",
                "meses_cobertura_objetivo", "stock_objetivo",
                "sugerencia_bruta", "sugerencia_final"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    df["cantidad_transito"] = df["cantidad_transito"].fillna(0)

    # Objetivo = (sellout_mes_ant_estimado + total_4_sem) / 2
    df["objetivo"] = ((df["sellout_mes_anterior_estimado"] + df["total_4_sem_verificado"]) / 2
                      ).round(0).astype(int)

    # Ritmo mensual para cobertura: máximo histórico de sellout
    sellout_cols = [c for c in df.columns if c.startswith("sellout_") and c != "sellout_mes_anterior_estimado"]
    if sellout_cols:
        for c in sellout_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        ritmo_mensual = df[sellout_cols].max(axis=1).replace(0, float("nan"))
    else:
        ritmo_mensual = (df["total_4_sem_verificado"] / 4 * 4.33).replace(0, float("nan"))

    # Cálculos de duración
    dur_solo_stock = (df["stock_act"] / ritmo_mensual).fillna(999)
    dur_total      = ((df["stock_act"] + df["cantidad_transito"]) / ritmo_mensual).fillna(999)

    # Duración a mostrar en el dashboard
    df["duracion_meses"] = dur_solo_stock
    if "nivel_alerta" in df.columns:
        df.loc[df["nivel_alerta"] == "MORADO", "duracion_meses"] = dur_total
    df["duracion_fisica_solo"] = dur_solo_stock

    # Diccionario de explicaciones de excepciones
    EXPLICACIONES = {
        "DATOS_INCOMPLETOS": "Faltan datos críticos (ej. nombre) o producto mal definido. Sugerencia de compra bloqueada.",
        "STOCK_NEGATIVO": "Stock físico negativo. Validar inventario físico antes de emitir compra.",
        "PRODUCTO_DESCONTINUADO": "Producto descontinuado. Compra automática bloqueada.",
        "SIN_UMP": "Existe necesidad de compra, pero falta Unidad Mínima de Pedido.",
        "SIN_ETA_TRANSITO": "Tránsito sin ETA: no se considera como mitigación de quiebre inmediato.",
        "SIN_VENTAS_SUFICIENTES": "Sin historial suficiente para proyectar demanda de manera confiable.",
        "PRODUCTO_NUEVO": "Producto nuevo. Requiere revisión de demanda antes de comprar."
    }

    # (Las variables sug_*, excepciones, requiere_revision, bloquea_compra_automatica
    # y nivel_alerta vienen ya calculadas desde el motor principal en planner.py)

    # Serializar
    all_cols = df.columns.tolist()
    records = []
    for _, row in df.iterrows():
        d = {}
        for c in all_cols:
            v = row[c]
            try:
                if isinstance(v, float) and math.isnan(v):
                    d[c] = None
                elif pd.isna(v):
                    d[c] = None
                elif isinstance(v, (pd.Timestamp, __import__('datetime').datetime, __import__('datetime').date)):
                    d[c] = v.isoformat()
                elif hasattr(v, "item"):
                    d[c] = v.item()
                else:
                    d[c] = v
            except Exception:
                d[c] = str(v) if v is not None else None

        row_dict = row.to_dict()
        cal = _build_month_calendar(all_cols, row_dict)
        d["calendario"]  = cal
        d["chart_12m"]   = _build_chart_12m(all_cols, row_dict)

        # Parsear excepciones
        import json
        try:
            excs = json.loads(d.get("excepciones", "[]"))
        except:
            excs = []
        d["excepciones"] = excs
        d["explicacion_excepcion"] = [EXPLICACIONES.get(code, code) for code in excs]
        
        records.append(d)

    return {"data": records, "total": len(records)}


@router.get("/categories")
def get_categories():
    with engine.connect() as conn:
        df = pd.read_sql(
            text("SELECT DISTINCT categoria, subcategoria, formato "
                 "FROM planificacion_sop ORDER BY categoria, subcategoria, formato NULLS LAST"),
            conn
        )
    tree = {}
    for _, row in df.iterrows():
        cat = row["categoria"] or "SIN CATEGORÍA"
        sub = row["subcategoria"] or "SIN SUBCATEGORÍA"
        fmt = row["formato"] or ""
        tree.setdefault(cat, {}).setdefault(sub, set())
        if fmt:
            tree[cat][sub].add(fmt)
    return {
        cat: {sub: sorted(list(fmts)) for sub, fmts in subs.items()}
        for cat, subs in sorted(tree.items())
    }


@router.get("/transito/{sku}")
def get_transito_sku(sku: str):
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT id, codigo_envio, nombre_pedido, cantidad,
                       fecha_eta,
                       COALESCE(eta_ajustada, fecha_disponibilidad_real) AS disp,
                       origen_eta, nombre_archivo, estado,
                       en_aforo, fecha_marcado_aforo, eta_ajustada
                FROM control_embarques
                WHERE sku = :s
                ORDER BY fecha_eta NULLS LAST
            """), conn, params={"s": sku})
    except Exception:
        return {"sku": sku, "ordenes": []}

    records = []
    for _, row in df.iterrows():
        records.append({
            "id":          int(row.get("id") or 0),
            "oc":          str(row.get("codigo_envio") or "—"),
            "nombre":      str(row.get("nombre_pedido") or "—"),
            "cantidad":    int(row.get("cantidad") or 0),
            "eta":         str(row.get("fecha_eta") or "")[:10] or "—",
            "disponible":  str(row.get("disp") or "")[:10] or "—",
            "origen":      str(row.get("origen_eta") or "—"),
            "estado":      str(row.get("estado") or "EN_TRANSITO"),
            "en_aforo":    bool(row.get("en_aforo")),
            "eta_ajustada": str(row.get("eta_ajustada") or "")[:10],
        })
    return {"sku": sku, "ordenes": records}


# ── Observaciones ─────────────────────────────────────────────────────────────
@router.get("/observacion/{sku}")
def get_observacion(sku: str):
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT observacion, usuario, fecha_modificacion "
                     "FROM sku_observaciones WHERE sku=:s"),
                {"s": sku}
            ).fetchone()
    except Exception:
        return {"sku": sku, "observacion": "", "usuario": None, "fecha": None}
    if not row:
        return {"sku": sku, "observacion": "", "usuario": None, "fecha": None}
    return {
        "sku":         sku,
        "observacion": row.observacion or "",
        "usuario":     row.usuario,
        "fecha":       str(row.fecha_modificacion)[:16] if row.fecha_modificacion else None,
    }


@router.post("/observacion/{sku}")
def save_observacion(
    sku: str,
    body: dict = Body(...),
    authorization: str = Header(None)
):
    """Guarda/actualiza observación de un SKU."""
    token   = _get_auth_header(authorization)
    payload = decode_token(token)
    permisos = payload.get("permisos", {})
    # Admin siempre puede; custom necesita can_edit_obs
    if payload.get("role") != "admin" and not permisos.get("can_edit_obs"):
        raise HTTPException(403, "Sin permiso para editar observaciones")

    obs     = body.get("observacion", "")
    usuario = payload.get("sub", "sistema")

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sku_observaciones (sku, observacion, usuario, fecha_modificacion)
            VALUES (:s, :o, :u, NOW())
            ON CONFLICT (sku) DO UPDATE
                SET observacion=EXCLUDED.observacion,
                    usuario=EXCLUDED.usuario,
                    fecha_modificacion=NOW()
        """), {"s": sku, "o": obs, "u": usuario})
    return {"ok": True, "sku": sku}
