"""
app.py — RRFF Soft Dashboard (v3.0)
=====================================
Correcciones:
  - Caché eliminada para reactividad total en filtros
  - Calendario fijo Ene-Dic con mapeo dinámico al año correcto
  - U/E desde columna ump de planificacion_sop (que toma gancheras de dim_productos)
  - Stock Físico desde stock_act (Excel manual)
  - Stock HC → "Pendiente de Mapeo" (columna aún no identificada en Matrix)
  - sellout/sellin desde planificacion_sop (planner output)
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from src.alerts import _build_engine, _extraer_sop, _extraer_transito, _calcular_metricas, _aplicar_reglas
except ImportError as e:
    st.error(f"Error importando módulos de backend: {e}")
    st.stop()

st.set_page_config(
    page_title="RRFF Soft - S&OP Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────
# CSS CORPORATIVO
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Cabecera de tarjeta */
.card-header {
    background-color: #dee2e6;
    padding: 9px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #adb5bd;
    border-radius: 6px 6px 0 0;
    margin-top: 24px;
}
.card-header span { font-size: 0.87rem; color: #212529; }
.card-header b { color: #1a3a5c; }

/* Etiqueta izquierda de fila de meses */
.row-label {
    font-size: 0.78rem; font-weight: 700; color: #495057;
    background-color: #f1f3f5;
    border-right: 2px solid #dee2e6;
    padding: 6px 4px; text-align: center;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center; gap: 14px;
    height: 100%;
}
.row-label .so { color: #c0392b; }
.row-label .si { color: #2980b9; }

/* Celda de mes */
.mes-cell {
    text-align: center; padding: 5px 2px;
    border-right: 1px solid #e9ecef; font-size: 0.82rem;
}
.mes-header { font-weight: 700; color: #1a3a5c; font-size: 0.77rem; }
.mes-so { color: #c0392b; font-weight: 600; font-size: 0.98rem; }
.mes-si { color: #2980b9; font-weight: 600; font-size: 0.98rem; }

/* Caja de métrica */
.m-box {
    padding: 11px 7px; border: 1px solid #dee2e6;
    border-radius: 6px; text-align: center;
    background: #fff; height: 100%;
}
.m-box .lbl { font-size: 0.74rem; color: #6c757d; margin-bottom: 3px; }
.m-box .val { font-size: 1.03rem; font-weight: 700; color: #212529; }
.m-box .sub { font-size: 0.78rem; color: #868e96; margin-top: 2px; }

/* Caja de alerta dinámica */
.alert-cell {
    padding: 11px 7px; border-radius: 6px;
    text-align: center; border: 1px solid rgba(0,0,0,0.08); height: 100%;
}
.alert-cell .lbl { font-size: 0.74rem; color: #495057; }
.alert-cell .val { font-size: 1.15rem; font-weight: 700; }
.alert-cell .nivel { font-size: 0.73rem; margin-top: 3px; }

/* Pendiente de mapeo */
.pending-box {
    padding: 11px 7px; border: 1px dashed #adb5bd;
    border-radius: 6px; text-align: center;
    background: #f8f9fa; height: 100%; opacity: 0.75;
}
.pending-box .lbl { font-size: 0.74rem; color: #6c757d; }
.pending-box .val { font-size: 0.82rem; color: #868e96; font-style: italic; margin-top: 4px; }

/* Semanas */
.sem-box {
    text-align: center; padding: 7px 3px;
    background: #f8f9fa; border-radius: 4px; border: 1px solid #e9ecef;
}
.sem-box .lbl { font-size: 0.73rem; color: #6c757d; }
.sem-box .val { font-weight: 700; font-size: 0.97rem; }
.obj-box {
    text-align: center; padding: 7px 3px;
    background: #eaf2f8; border-radius: 4px; border: 1px solid #bce0fd;
}
.obj-box .lbl { font-size: 0.73rem; color: #2980b9; font-weight: 700; }
.obj-box .val { font-weight: 700; font-size: 0.97rem; color: #154360; }

hr.sep { border: none; border-top: 1px dashed #ced4da; margin: 6px 0 20px 0; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
COLORES_ALERTA = {
    'ROJO':    '#ffcccc',
    'NARANJA': '#ffe6cc',
    'AMARILLO':'#ffffcc',
    'AZUL':    '#cce5ff',
    'MORADO':  '#ecc6ec',
    'VERDE':   '#d4edda',
}
EMOJI_NIVEL = {
    'ROJO':'🔴','NARANJA':'🟠','AMARILLO':'🟡',
    'AZUL':'🔵','MORADO':'🟣','VERDE':'🟢',
}

# Calendario Ene-Dic en orden fijo. El año se detecta dinámicamente.
MESES_ORDEN = [
    ("Ene", "ene"), ("Feb", "feb"), ("Mar", "mar"), ("Abr", "abr"),
    ("May", "may"), ("Jun", "jun"), ("Jul", "jul"), ("Ago", "ago"),
    ("Sep", "sep"), ("Oct", "oct"), ("Nov", "nov"), ("Dic", "dic"),
]

def _safe_int(v, d=0):
    try: return d if pd.isna(v) else int(v)
    except: return d

def _safe_float(v, d=0.0):
    try: return d if pd.isna(v) else float(v)
    except: return d

def _find_col(cols, prefix, abrev):
    """Busca una columna como 'sellout_ene_XXXX' sin importar el año."""
    for c in cols:
        if c.startswith(f"{prefix}_{abrev}_"):
            return c
    return None


# ──────────────────────────────────────────────────────────────────
# CARGA DE DATOS — sin caché para reactividad total
# ──────────────────────────────────────────────────────────────────
@st.cache_resource
def _get_engine():
    """Engine singleton reutilizable (solo conexión, no datos)."""
    return _build_engine()


def load_all_data():
    """Carga fresca de datos desde PostgreSQL. Sin caché para garantizar reactividad."""
    engine = _get_engine()
    df_sop      = _extraer_sop(engine)
    df_transito = _extraer_transito(engine)

    # Tránsito completo para desglose OC
    try:
        df_tr_full = pd.read_sql("SELECT * FROM fact_transito", engine)
    except Exception:
        df_tr_full = pd.DataFrame()

    # Métricas y alertas
    df_metrics  = _calcular_metricas(df_sop, df_transito)
    df_alertas  = _aplicar_reglas(df_metrics)

    df = pd.merge(
        df_metrics,
        df_alertas[['sku', 'nivel_alerta', 'alertas']],
        on='sku', how='left'
    )
    df['nivel_alerta']  = df['nivel_alerta'].fillna('VERDE')
    df['alertas']       = df['alertas'].fillna('Normal')

    # fillna estratégico — NUNCA eliminar filas por campos descriptivos nulos
    df['categoria']     = df['categoria'].fillna('SIN CATEGORÍA')
    df['subcategoria']  = df['subcategoria'].fillna('SIN SUBCATEGORÍA')
    df['nombre_producto'] = df['nombre_producto'].fillna('—')
    df['codigo_femaco'] = df['codigo_femaco'].fillna('—')

    return df, df_tr_full


# ──────────────────────────────────────────────────────────────────
# TÍTULO
# ──────────────────────────────────────────────────────────────────
st.title("RRFF Soft — Planificación S&OP (Vista Excel)")

with st.spinner("Conectando a PostgreSQL..."):
    try:
        df, df_tr_full = load_all_data()
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        st.stop()

all_cols = df.columns.tolist()


# ──────────────────────────────────────────────────────────────────
# BARRA LATERAL — FILTROS JERÁRQUICOS REACTIVOS CON RESET AUTOMÁTICO
# ──────────────────────────────────────────────────────────────────
st.sidebar.header("🔎 Filtros de Navegación")

# Callbacks de reset jerárquico
def _reset_sub_sku():
    st.session_state["_sub_val"] = "TODAS"
    st.session_state["_sku_val"] = "TODOS"

def _reset_sku_only():
    st.session_state["_sku_val"] = "TODOS"

# Inicializar estado de selección
if "_cat_val" not in st.session_state: st.session_state["_cat_val"] = "TODAS"
if "_sub_val" not in st.session_state: st.session_state["_sub_val"] = "TODAS"
if "_sku_val" not in st.session_state: st.session_state["_sku_val"] = "TODOS"

# 1. CATEGORÍA
categorias = ["TODAS"] + sorted(df['categoria'].dropna().unique().tolist())

# Validar que el valor guardado sigue siendo válido
if st.session_state["_cat_val"] not in categorias:
    st.session_state["_cat_val"] = "TODAS"
    st.session_state["_sub_val"] = "TODAS"
    st.session_state["_sku_val"] = "TODOS"

# Detectar cambio manual usando el valor anterior
cat_prev = st.session_state["_cat_val"]
sel_cat = st.sidebar.selectbox("1. Categoría", options=categorias, index=categorias.index(st.session_state["_cat_val"]))

if sel_cat != cat_prev:    # La categoría cambió → resetear hijos
    st.session_state["_cat_val"] = sel_cat
    st.session_state["_sub_val"] = "TODAS"
    st.session_state["_sku_val"] = "TODOS"
    st.rerun()

df_cat = df if sel_cat == "TODAS" else df[df['categoria'] == sel_cat]

# 2. SUBCATEGORÍA — sólo opciones válidas para la categoría
subcats = ["TODAS"] + sorted(df_cat['subcategoria'].dropna().unique().tolist())

if st.session_state["_sub_val"] not in subcats:
    st.session_state["_sub_val"] = "TODAS"
    st.session_state["_sku_val"] = "TODOS"

sub_prev = st.session_state["_sub_val"]
sel_sub = st.sidebar.selectbox("2. Subcategoría", options=subcats, index=subcats.index(st.session_state["_sub_val"]))

if sel_sub != sub_prev:    # La subcategoría cambió → resetear SKU
    st.session_state["_sub_val"] = sel_sub
    st.session_state["_sku_val"] = "TODOS"
    st.rerun()

df_sub = df_cat if sel_sub == "TODAS" else df_cat[df_cat['subcategoria'] == sel_sub]

# 3. SKU específico
skus = ["TODOS"] + sorted(df_sub['sku'].astype(str).unique().tolist())

if st.session_state["_sku_val"] not in skus:
    st.session_state["_sku_val"] = "TODOS"

sel_sku = st.sidebar.selectbox("3. SKU", options=skus, index=skus.index(st.session_state["_sku_val"]))
st.session_state["_sku_val"] = sel_sku

# DataFrame final a renderizar
filtered = df_sub if sel_sku == "TODOS" else df_sub[df_sub['sku'].astype(str) == sel_sku]

st.sidebar.divider()
st.sidebar.metric("Productos", len(filtered))
for niv in ['ROJO', 'NARANJA']:
    n = (filtered['nivel_alerta'] == niv).sum()
    if n: st.sidebar.markdown(f"{EMOJI_NIVEL[niv]} **{niv}**: {n}")

# ──────────────────────────────────────────────────────────────────
# GUARDIA: sin resultados
# ──────────────────────────────────────────────────────────────────
if filtered.empty:
    st.info("Sin productos para los filtros seleccionados.")
    st.stop()


# ──────────────────────────────────────────────────────────────────
# BUCLE DE TARJETAS
# ──────────────────────────────────────────────────────────────────
for _, row in filtered.iterrows():
    sku        = str(row.get('sku', '—'))
    femaco     = str(row.get('codigo_femaco', '—'))
    desc       = str(row.get('nombre_producto', '—'))
    nivel      = str(row.get('nivel_alerta', 'VERDE'))
    color_bg   = COLORES_ALERTA.get(nivel, '#fff')
    emoji_niv  = EMOJI_NIVEL.get(nivel, '⬜')

    # ── U/E: columna ump de planificacion_sop (= gancheras de dim_productos) ──
    ump_raw    = row.get('ump', None)
    ue_val     = _safe_float(ump_raw)
    ue_display = str(int(ue_val)) if ue_val > 0 else "—"

    # ── Stock Físico: stock_act del Excel manual (intransigente) ────────────
    stock_act  = _safe_int(row.get('stock_act', 0))
    cajas      = int(stock_act // ue_val) if ue_val > 0 else 0

    # ── Tránsito ────────────────────────────────────────────────────────────
    cant_tr    = _safe_float(row.get('cantidad_transito', 0))
    eta_str    = str(row.get('fecha_disponibilidad_real', ''))
    if not eta_str or eta_str in ('None', 'nan', ''): eta_str = 'Sin tránsito'

    # ── Duración ─────────────────────────────────────────────────────────────
    dur_proy   = _safe_float(row.get('duracion_proyectada_meses', 0))
    dur_str    = "∞" if dur_proy >= 999 else f"{dur_proy:.1f} m"

    # ── Sell-Out max/min desde planificacion_sop ─────────────────────────────
    max_so     = _safe_int(row.get('valor_pico_sellout_uds', 0))
    min_so     = _safe_int(row.get('sellout_minimo', 0))
    mes_pico   = str(row.get('mes_pico_sellout', '—'))[:10]

    # ── Sugerencia de compra (múltiplo UMP via math.ceil) ─────────────────
    sug        = _safe_int(row.get('sugerencia_compra_inmediata_uds', 0))

    # ── Tránsito detalle OC ─────────────────────────────────────────────────
    oc_rows = pd.DataFrame()
    if not df_tr_full.empty and 'sku' in df_tr_full.columns:
        oc_rows = df_tr_full[df_tr_full['sku'].astype(str) == sku]

    # ═══════════════════════════════════════════════════════════════════
    # TARJETA
    # ═══════════════════════════════════════════════════════════════════
    with st.container():

        # ── FILA 1: CABECERA GRIS ────────────────────────────────────
        cat_label  = str(row.get('categoria', '—'))
        sub_label  = str(row.get('subcategoria', '—'))
        estado     = str(row.get('estado', ''))
        st.markdown(f"""
        <div class="card-header">
            <span><b>SKU</b> {sku} &nbsp;|&nbsp; <b>CÓD.</b> {femaco}</span>
            <span style="flex:2; text-align:center;"><b>{desc}</b></span>
            <span>{cat_label} › {sub_label}</span>
            <span><b>U/E</b> {ue_display}</span>
        </div>
        """, unsafe_allow_html=True)

        # ── FILA 2: CALENDARIO MENSUAL ENE-DIC (fijo) ─────────────
        # Columna de etiquetas + 12 meses
        lbl_col, *mcols = st.columns([0.65] + [1]*12)
        with lbl_col:
            st.markdown("""
            <div class="row-label">
                <span class="so">Sell Out</span>
                <span class="si">Sell In</span>
            </div>
            """, unsafe_allow_html=True)

        for i, (mes_lbl, mes_abr) in enumerate(MESES_ORDEN):
            c_so = _find_col(all_cols, "sellout", mes_abr)
            c_si = _find_col(all_cols, "sellin",  mes_abr)
            so   = _safe_int(row.get(c_so, 0)) if c_so else 0
            si   = _safe_int(row.get(c_si, 0)) if c_si else 0
            with mcols[i]:
                st.markdown(f"""
                <div class="mes-cell">
                    <div class="mes-header">{mes_lbl}</div>
                    <div class="mes-so">{so:,}</div>
                    <div class="mes-si">{si:,}</div>
                </div>
                """, unsafe_allow_html=True)

        # ── FILA 3: MÉTRICAS DE CONTROL ──────────────────────────
        st.write("")
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        # C1: Stock Físico Femaco (del Excel manual - stock_act)
        with c1:
            st.markdown(f"""
            <div class="m-box">
                <div class="lbl">📦 Stock Físico (Femaco)</div>
                <div class="val">{stock_act:,} <small style="font-size:0.75rem;color:#aaa;">uds</small></div>
                <div class="sub">{cajas} cajas · U/E {ue_display}</div>
            </div>
            """, unsafe_allow_html=True)

        # C2: Stock HC — Pendiente de Mapeo (columna Matrix no identificada)
        with c2:
            st.markdown("""
            <div class="pending-box">
                <div class="lbl">🏪 Stock HC (Tiendas)</div>
                <div class="val">⏳ Pendiente de Mapeo</div>
            </div>
            """, unsafe_allow_html=True)

        # C3: Tránsito total + expander de detalle OC
        with c3:
            st.markdown(f"""
            <div class="m-box">
                <div class="lbl">🚢 Tránsito Total</div>
                <div class="val">{int(cant_tr):,} <small style="font-size:0.75rem;color:#aaa;">uds</small></div>
                <div class="sub">ETA: {eta_str}</div>
            </div>
            """, unsafe_allow_html=True)

        # C4: Sell-Out Máx / Mín
        with c4:
            min_str = f"{min_so:,}" if min_so > 0 else "—"
            st.markdown(f"""
            <div class="m-box">
                <div class="lbl">📊 Sell-Out Máx / Mín</div>
                <div class="val">{max_so:,}</div>
                <div class="sub">Mín: {min_str} · {mes_pico}</div>
            </div>
            """, unsafe_allow_html=True)

        # C5: Duración & Semáforo
        with c5:
            st.markdown(f"""
            <div class="alert-cell" style="background-color:{color_bg};">
                <div class="lbl">Duración & Estado</div>
                <div class="val">{dur_str}</div>
                <div class="nivel">{emoji_niv} {nivel}</div>
            </div>
            """, unsafe_allow_html=True)

        # C6: Sugerencia de compra (múltiplo UMP)
        with c6:
            st.markdown(f"""
            <div class="m-box" style="border:2px solid #2ecc71;">
                <div class="lbl">🛒 Sugerencia Compra</div>
                <div class="val" style="color:#27ae60;font-size:1.15rem;">{sug:,}</div>
                <div class="sub">unidades (×U/E)</div>
            </div>
            """, unsafe_allow_html=True)

        # ── DESGLOSE DE TRÁNSITO (expander por OC) ───────────────
        if not oc_rows.empty:
            total_oc = int(oc_rows['cantidad_transito'].sum()) if 'cantidad_transito' in oc_rows.columns else 0
            with st.expander(f"📋 Ver desglose de tránsito — {len(oc_rows)} OC{'s' if len(oc_rows)>1 else ''} · {total_oc:,} uds"):
                for _, oc in oc_rows.iterrows():
                    oc_num  = str(oc.get('codigo_envio', '—'))
                    oc_cant = _safe_int(oc.get('cantidad_transito', 0))
                    oc_eta  = str(oc.get('fecha_eta', '—'))
                    oc_disp = str(oc.get('fecha_disponibilidad_real', '—'))
                    orig    = str(oc.get('origen_eta', '—'))
                    st.markdown(
                        f"&nbsp;&nbsp;🚢 **{oc_num}** — `{oc_cant:,} uds` — "
                        f"ETA: `{oc_eta}` → Disponible: `{oc_disp}` _{orig}_"
                    )

        # ── FILA 4: VENTAS CORTO PLAZO ───────────────────────────
        st.write("")
        st.markdown("**Ventas Corto Plazo — Últimas 4 Semanas**")
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)

        def _sem(col_obj, label, val):
            col_obj.markdown(f"""
            <div class="sem-box">
                <div class="lbl">{label}</div>
                <div class="val">{_safe_int(val):,}</div>
            </div>
            """, unsafe_allow_html=True)

        _sem(sc1, "Semana 1",  row.get('sem1_uds', 0))
        _sem(sc2, "Semana 2",  row.get('sem2_uds', 0))
        _sem(sc3, "Semana 3",  row.get('sem3_uds', 0))
        _sem(sc4, "Semana 4",  row.get('sem4_uds', 0))
        _sem(sc5, "Total 4 Sem", row.get('total_4_sem_verificado', 0))

        ritmo_m = int(_safe_float(row.get('ritmo_semanal_uds', 0)) * 4.33)
        sc6.markdown(f"""
        <div class="obj-box">
            <div class="lbl">Objetivo (Ritmo)</div>
            <div class="val">{ritmo_m:,}</div>
        </div>
        """, unsafe_allow_html=True)

        # Alertas al pie
        alertas_txt = str(row.get('alertas', ''))
        if alertas_txt and alertas_txt != 'Normal':
            st.caption(f"⚠️ {alertas_txt[:250]}")

        st.markdown("<hr class='sep'>", unsafe_allow_html=True)
