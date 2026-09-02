"""
alerts.py — Módulo de Alertas RRFF Soft  (Fase 5)
===================================================
Extrae planificacion_sop + fact_transito, aplica 5 reglas de riesgo y
exporta alertas_riesgo.csv + envío SMTP opcional.

REGLAS DE RIESGO:
  R1 — Quiebre Crítico (stock físico):
       duracion_stock_fisico <= 3 meses

  R2 — Sobre-stock / Lento Movimiento:
       duracion_stock_fisico > 10 meses  (sin considerar tránsito)

  R3 — Volatilidad Extrema:
       CV_ritmo >= 0.25 (aceleración) o el ritmo semanal cayó > 50%

  R4 — ALERTA ROJA: Quiebre Inminente Físico (antes del barco):
       El stock físico se agota ANTES de fecha_disponibilidad_real (ETA + 14d).
       Es decir: dias_cobertura_fisica < dias_hasta_disponibilidad.

  R5 — ALERTA AMARILLA: Pedir Ahora (tránsito salva la urgencia, pero ciclo corto):
       duracion_proyectada (físico + tránsito) < 4 meses.
       Indica que hay que emitir nueva OC inmediatamente.

JERARQUÍA DE PRIORIDAD: R4 > R1 > R5 > R3 > R2
"""

import logging
import os
import smtplib
import sys
from datetime import date, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
PROC_DIR    = BASE_DIR / "data" / "processed"
OUTPUT_FILE = PROC_DIR / "alertas_riesgo.csv"

TABLA_SOP      = "planificacion_sop"
TABLA_TRANSITO = "fact_transito"

# Umbrales
R1_QUIEBRE_FISICO   = 3.0    # meses de stock físico mínimo
R2_SOBRESTOCK       = 10.0   # meses de stock físico máximo
R3_CV_ALZA          = 0.25   # coeficiente de variación (aceleración)
R5_PEDIR_AHORA      = 4.0    # meses de cobertura proyectada (físico+tránsito)
DIAS_AFORO          = 14     # días de buffer de aforo (ya sumados en ETA)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ALERTS] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("alerts")


# ──────────────────────────────────────────────────────────────────────────────
def _build_engine():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        eng = create_engine(
            db_url,
            connect_args={"connect_timeout": 10},
            pool_pre_ping=True,
        )
        with eng.connect() as c:
            ver = c.execute(text("SELECT version()")).scalar()
            log.info("Conexion OK via DATABASE_URL: %s", ver[:55])
        return eng

    host = os.getenv("DB_HOST", "localhost").strip().strip('"')
    port = os.getenv("DB_PORT", "5432").strip().strip('"')
    name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
    user = os.getenv("DB_USER", "postgres").strip().strip('"')
    pwd_env = os.getenv("DB_PASS")
    if not pwd_env:
        raise RuntimeError("Falta DB_PASS; configura DATABASE_URL o las variables DB_*")
    pwd = pwd_env.strip().strip('"')
    eng  = create_engine(
        f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}",
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,
    )
    with eng.connect() as c:
        ver = c.execute(text("SELECT version()")).scalar()
        log.info("Conexion OK: %s", ver[:55])
    return eng


def _extraer_sop(engine) -> pd.DataFrame:
    log.info("Extrayendo planificacion_sop...")
    df = pd.read_sql(f"SELECT * FROM {TABLA_SOP}", engine)
    log.info("  %d filas x %d columnas cargadas.", *df.shape)
    return df


def _extraer_transito(engine) -> pd.DataFrame:
    """Extrae fact_transito. Devuelve DataFrame vacío si la tabla no existe."""
    log.info("Extrayendo fact_transito...")
    try:
        df = pd.read_sql(f"SELECT * FROM {TABLA_TRANSITO}", engine)
        log.info("  %d líneas de tránsito cargadas.", len(df))
        return df
    except Exception as exc:
        log.warning("fact_transito no disponible (%s). Alertas R4/R5 no se aplicarán.", exc)
        return pd.DataFrame()


def _calcular_metricas(df: pd.DataFrame, df_transito: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula todas las métricas de riesgo por SKU:
      - ritmo_mensual
      - duracion_stock_fisico_meses
      - cv_ritmo
      - cantidad_transito (agregada por SKU desde fact_transito)
      - fecha_disponibilidad_real (la más próxima entre OCs del SKU)
      - stock_total_proyectado
      - duracion_proyectada_meses
    """
    hoy = date.today()

    # Ritmo mensual (suma de 4 semanas)
    df["ritmo_mensual"] = df[["sem1_uds", "sem2_uds", "sem3_uds", "sem4_uds"]].fillna(0).sum(axis=1)

    # Duración stock físico
    df["duracion_stock_fisico_meses"] = (
        df["stock_act"] / df["ritmo_mensual"].replace(0.0, float("nan"))
    ).round(2)
    df.loc[df["ritmo_mensual"] == 0, "duracion_stock_fisico_meses"] = 999.0

    # CV ritmo entre las 4 semanas
    sem_cols = ["sem1_uds", "sem2_uds", "sem3_uds", "sem4_uds"]
    sem_data = df[sem_cols].copy()
    sem_mean = sem_data.mean(axis=1).replace(0, float("nan"))
    df["cv_ritmo"] = ((sem_data.max(axis=1) - sem_data.min(axis=1)) / sem_mean).round(4).fillna(0.0)

    # Columnas de tránsito por defecto
    df["cantidad_transito"]        = 0.0
    df["fecha_disponibilidad_real"] = None

    # Cruzar con tránsito si existe
    if not df_transito.empty and "sku" in df_transito.columns:
        df_transito_clean = df_transito[df_transito["sku"].notna()].copy()

        # Parsear fecha_disponibilidad_real
        df_transito_clean["fdr"] = pd.to_datetime(
            df_transito_clean["fecha_disponibilidad_real"],
            errors="coerce"
        )

        # Agregar por SKU: suma cantidades + ETA más próxima
        agg = df_transito_clean.groupby("sku").agg(
            cantidad_transito=("cantidad_transito", "sum"),
            fecha_disponibilidad_real=("fdr", "min"),   # la más próxima
        ).reset_index()

        df = df.merge(agg, on="sku", how="left", suffixes=("", "_tr"))

        # Resolver columnas tras el merge
        if "cantidad_transito_tr" in df.columns:
            df["cantidad_transito"] = df["cantidad_transito_tr"].fillna(0.0)
            df.drop(columns=["cantidad_transito_tr"], inplace=True)
        else:
            df["cantidad_transito"] = df["cantidad_transito"].fillna(0.0)

        if "fecha_disponibilidad_real_tr" in df.columns:
            df["fecha_disponibilidad_real"] = df["fecha_disponibilidad_real_tr"]
            df.drop(columns=["fecha_disponibilidad_real_tr"], inplace=True)

    # Stock total proyectado
    df["stock_total_proyectado"] = df["stock_act"] + df["cantidad_transito"].fillna(0)

    # Duración proyectada (físico + tránsito)
    df["duracion_proyectada_meses"] = (
        df["stock_total_proyectado"] / df["ritmo_mensual"].replace(0.0, float("nan"))
    ).round(2)
    df.loc[df["ritmo_mensual"] == 0, "duracion_proyectada_meses"] = 999.0

    # Días de cobertura física (para R4)
    df["dias_cobertura_fisica"] = (df["duracion_stock_fisico_meses"] * 30.4).round(0)

    # Días hasta disponibilidad real (para R4)
    def _dias_hasta_disponible(fdr):
        if fdr is None or pd.isna(fdr):
            return None
        try:
            return (pd.Timestamp(fdr).date() - hoy).days
        except Exception:
            return None

    df["dias_hasta_disponibilidad"] = df["fecha_disponibilidad_real"].apply(_dias_hasta_disponible)

    log.info("  Stock físico medio:      %.1f uds", df["stock_act"].mean())
    log.info("  Tránsito medio:          %.1f uds", df["cantidad_transito"].mean())
    log.info("  Stock proyectado medio:  %.1f uds", df["stock_total_proyectado"].mean())
    log.info("  Duración física media:   %.1f m",
             df["duracion_stock_fisico_meses"].replace(999.0, float("nan")).mean())
    log.info("  Duración proyectada med: %.1f m",
             df["duracion_proyectada_meses"].replace(999.0, float("nan")).mean())

    return df


def _aplicar_reglas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las 5 reglas y construye el DataFrame de alertas.
    La columna 'alertas' contiene todas las reglas activas separadas por ' | '.
    La columna 'nivel_max' refleja la severidad máxima: ROJO > NARANJA > AMARILLO.
    """
    alertas_rows = []
    hoy = date.today()

    for _, row in df.iterrows():
        reglas_activas = []
        nivel = "VERDE"

        dur_fis = row.get("duracion_stock_fisico_meses") or 0.0
        dur_proy = row.get("duracion_proyectada_meses") or 0.0
        cv      = row.get("cv_ritmo") or 0.0
        dias_fis = row.get("dias_cobertura_fisica") or 0.0
        dias_disp = row.get("dias_hasta_disponibilidad")
        cant_tr  = row.get("cantidad_transito") or 0.0

        # ── R4: ALERTA ROJA — Quiebre Físico ANTES del Barco ─────────────────
        if (dias_disp is not None
                and not pd.isna(dias_disp)
                and cant_tr > 0
                and dias_fis < dias_disp):
            reglas_activas.append(
                f"🔴 ALERTA ROJA: Quiebre Físico Antes de Llegada "
                f"(stock dura {int(dias_fis)}d, barco llega en {int(dias_disp)}d)"
            )
            nivel = "ROJO"

        # ── R1: Quiebre Crítico (stock físico <= 3 meses) ────────────────────
        elif dur_fis <= R1_QUIEBRE_FISICO and dur_fis != 999.0:
            reglas_activas.append(
                f"🟠 ALERTA: Quiebre Crítico (cobertura física {dur_fis:.1f}m)"
            )
            if nivel != "ROJO":
                nivel = "NARANJA"

        # ── R5: ALERTA AMARILLA — Tránsito salva urgencia, pero hay que pedir ─
        if (dur_proy < R5_PEDIR_AHORA
                and dur_proy != 999.0
                and cant_tr > 0):
            reglas_activas.append(
                f"🟡 ALERTA AMARILLA: Pedir Ahora — "
                f"Proyectado {dur_proy:.1f}m con tránsito (Lead Time < 4m)"
            )
            if nivel not in ("ROJO", "NARANJA"):
                nivel = "AMARILLO"

        # ── R2: Sobre-stock / Lento movimiento ──────────────────────────────
        if dur_fis > R2_SOBRESTOCK:
            reglas_activas.append(
                f"🔵 ALERTA: Exceso de Inventario / Lento Movimiento "
                f"(cobertura {dur_fis:.0f}m)"
            )
            if nivel == "VERDE":
                nivel = "AZUL"

        # ── R3: Volatilidad Extrema ───────────────────────────────────────────
        if cv >= R3_CV_ALZA:
            reglas_activas.append(
                f"🟣 ALERTA: Volatilidad Extrema (CV={cv:.2f})"
            )
            if nivel == "VERDE":
                nivel = "MORADO"

        if reglas_activas:
            fdr = row.get("fecha_disponibilidad_real")
            alertas_rows.append({
                "fecha_analisis"              : hoy.isoformat(),
                "nivel_alerta"                : nivel,
                "sku"                         : row["sku"],
                "codigo_femaco"               : row.get("codigo_femaco", ""),
                "nombre_producto"             : row["nombre_producto"],
                "categoria"                   : row.get("categoria", ""),
                "stock_act"                   : row["stock_act"],
                "cantidad_transito"           : cant_tr,
                "stock_total_proyectado"      : row["stock_total_proyectado"],
                "ritmo_semanal_uds"           : row["ritmo_semanal_uds"],
                "ritmo_mensual_uds"           : round(row["ritmo_mensual"], 1),
                "duracion_stock_fisico_meses" : dur_fis if dur_fis < 900 else 999.0,
                "duracion_proyectada_meses"   : dur_proy if dur_proy < 900 else 999.0,
                "dias_cobertura_fisica"       : int(dias_fis) if dias_fis < 9000 else 9999,
                "dias_hasta_disponibilidad"   : int(dias_disp) if dias_disp is not None and not pd.isna(dias_disp) else None,
                "fecha_disponibilidad_real"   : str(fdr) if fdr else None,
                "cv_ritmo"                    : cv,
                "sem1_uds"                    : row.get("sem1_uds", 0),
                "sem2_uds"                    : row.get("sem2_uds", 0),
                "sem3_uds"                    : row.get("sem3_uds", 0),
                "sem4_uds"                    : row.get("sem4_uds", 0),
                "total_4_sem_verificado"      : row.get("total_4_sem_verificado", 0),
                "yoy_sellout_pct"             : row.get("yoy_sellout_pct", None),
                "mes_pico_sellout"            : row.get("mes_pico_sellout", ""),
                "sugerencia_compra_inmediata" : row.get("sugerencia_compra_inmediata_uds", 0),
                "ump"                         : row.get("ump", None),
                "alertas"                     : " | ".join(reglas_activas),
                "n_alertas"                   : len(reglas_activas),
            })

    return pd.DataFrame(alertas_rows)


def _exportar_csv(df_alertas: pd.DataFrame) -> Path:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    df_alertas.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig", sep=";")
    log.info("CSV exportado: %s  (%d bytes)", OUTPUT_FILE, OUTPUT_FILE.stat().st_size)
    return OUTPUT_FILE


def _enviar_email(df_alertas: pd.DataFrame, csv_path: Path) -> bool:
    load_dotenv()
    smtp_server = os.getenv("SMTP_SERVER", "").strip()
    smtp_port   = int(os.getenv("SMTP_PORT", "587"))
    smtp_user   = os.getenv("SMTP_USER", "").strip()
    smtp_pass   = os.getenv("SMTP_PASS", "").strip()
    dest_email  = os.getenv("ALERT_DEST_EMAIL", smtp_user).strip()

    if not smtp_server or not smtp_user or not smtp_pass:
        log.warning("SMTP no configurado. Correo NO enviado. CSV disponible en /data/processed.")
        return False

    hoy  = date.today().isoformat()
    n    = len(df_alertas)
    r4_n = df_alertas["alertas"].str.contains("ROJA", na=False).sum()
    r1_n = df_alertas["alertas"].str.contains("Quiebre Crítico", na=False).sum()
    r5_n = df_alertas["alertas"].str.contains("AMARILLA", na=False).sum()
    r2_n = df_alertas["alertas"].str.contains("Exceso", na=False).sum()
    r3_n = df_alertas["alertas"].str.contains("Volatilidad", na=False).sum()

    def _tabla_html(sub, cols, max_rows=8):
        sub = sub[cols].head(max_rows)
        header = "".join(f"<th style='background:#1a3a5c;color:#fff;padding:5px;border:1px solid #ddd'>{c}</th>" for c in cols)
        rows_html = "".join(
            f"<tr>{''.join(f'<td style=padding:4px;border:1px solid #ddd>{v}</td>' for v in r)}</tr>"
            for r in sub.values
        )
        return f"<table style='border-collapse:collapse;font-size:11px;width:100%;margin-bottom:12px'><tr>{header}</tr>{rows_html}</table>"

    r4 = df_alertas[df_alertas["nivel_alerta"] == "ROJO"]
    r1 = df_alertas[df_alertas["nivel_alerta"] == "NARANJA"]
    r5 = df_alertas[df_alertas["nivel_alerta"] == "AMARILLO"]

    cols_tbl = ["sku", "nombre_producto", "stock_act", "cantidad_transito",
                "duracion_stock_fisico_meses", "fecha_disponibilidad_real", "alertas"]

    html = f"""<html><body style="font-family:Arial,sans-serif;color:#222">
    <h2 style="color:#c0392b">⚠️ Reporte de Alertas RRFF Soft — {hoy}</h2>
    <p>Motor de riesgo detectó <strong>{n} productos</strong> bajo condición de alerta.</p>
    <table style="border-collapse:collapse;margin-bottom:16px">
      <tr><td style="padding:6px 12px;background:#e74c3c;color:#fff;border-radius:4px">🔴 Quiebre Físico Antes del Barco</td><td style="padding:6px 16px"><b>{r4_n}</b> SKUs</td></tr>
      <tr><td style="padding:6px 12px;background:#e67e22;color:#fff;border-radius:4px">🟠 Quiebre Crítico Físico (≤3m)</td><td style="padding:6px 16px"><b>{r1_n}</b> SKUs</td></tr>
      <tr><td style="padding:6px 12px;background:#f1c40f;color:#333;border-radius:4px">🟡 Pedir Ahora (proyectado &lt;4m)</td><td style="padding:6px 16px"><b>{r5_n}</b> SKUs</td></tr>
      <tr><td style="padding:6px 12px;background:#3498db;color:#fff;border-radius:4px">🔵 Sobre-stock / Lento Movimiento</td><td style="padding:6px 16px"><b>{r2_n}</b> SKUs</td></tr>
      <tr><td style="padding:6px 12px;background:#8e44ad;color:#fff;border-radius:4px">🟣 Volatilidad Extrema</td><td style="padding:6px 16px"><b>{r3_n}</b> SKUs</td></tr>
    </table>
    {"<h3 style='color:#e74c3c'>🔴 Quiebre Físico Antes del Barco</h3>" + _tabla_html(r4, cols_tbl) if len(r4) else ""}
    {"<h3 style='color:#e67e22'>🟠 Quiebre Crítico</h3>" + _tabla_html(r1, cols_tbl) if len(r1) else ""}
    {"<h3 style='color:#b7950b'>🟡 Pedir Ahora</h3>" + _tabla_html(r5, cols_tbl) if len(r5) else ""}
    <p style="color:#888;font-size:11px;margin-top:24px">Generado por RRFF Soft Pipeline v3.0 · {hoy}<br>Adjunto: alertas_riesgo.csv</p>
    </body></html>"""

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[RRFF Soft] ⚠️ {n} alertas ({r4_n} ROJAS) — {hoy}"
    msg["From"]    = smtp_user
    msg["To"]      = dest_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={csv_path.name}")
    msg.attach(part)

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo(); server.starttls(); server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, dest_email, msg.as_string())
        log.info("Correo enviado a %s", dest_email)
        return True
    except Exception as exc:
        log.error("Error al enviar correo: %s", exc)
        return False


# ──────────────────────────────────────────────────────────────────────────────
def run_alerts(sop_data=None) -> dict:
    """Ejecuta el motor de alertas completo (Fase 5)."""
    log.info("=" * 60)
    log.info("FASE 5 - Motor de Alertas con Dimensión de Tránsito")
    log.info("Fecha: %s", date.today().isoformat())
    log.info("=" * 60)

    engine = _build_engine()

    log.info("--- [5.1] Extraccion de datos ---")
    df          = _extraer_sop(engine)
    df_transito = _extraer_transito(engine)
    engine.dispose()

    log.info("--- [5.2] Calculo de metricas con tránsito ---")
    df = _calcular_metricas(df, df_transito)

    log.info("--- [5.3] Motor de reglas (5 reglas) ---")
    df_alertas = _aplicar_reglas(df)

    # Conteos por regla
    r4_n = df_alertas["alertas"].str.contains("ROJA",         na=False).sum()
    r1_n = df_alertas["alertas"].str.contains("Quiebre Crít", na=False).sum()
    r5_n = df_alertas["alertas"].str.contains("AMARILLA",     na=False).sum()
    r2_n = df_alertas["alertas"].str.contains("Exceso",       na=False).sum()
    r3_n = df_alertas["alertas"].str.contains("Volatilidad",  na=False).sum()

    log.info("  R4 ROJA (barco tarde):    %d SKUs", r4_n)
    log.info("  R1 Quiebre Critico:       %d SKUs", r1_n)
    log.info("  R5 AMARILLA (pedir ya):   %d SKUs", r5_n)
    log.info("  R2 Sobre-stock:           %d SKUs", r2_n)
    log.info("  R3 Volatilidad:           %d SKUs", r3_n)
    log.info("  TOTAL alertas unicas:     %d SKUs", len(df_alertas))

    # Preview por nivel
    if not df_alertas.empty:
        log.info("  Preview por nivel:")
        for nivel, emoji in [("ROJO","🔴"),("NARANJA","🟠"),("AMARILLO","🟡")]:
            sub = df_alertas[df_alertas["nivel_alerta"] == nivel].head(3)
            for _, r in sub.iterrows():
                log.info("    %s %-10s | %-30s | Fís=%.1fm | Proy=%.1fm | Tranx=%s | ETA_disp=%s",
                         emoji, r["sku"], r["nombre_producto"][:30],
                         r["duracion_stock_fisico_meses"],
                         r["duracion_proyectada_meses"],
                         r["cantidad_transito"],
                         r["fecha_disponibilidad_real"])

    log.info("--- [5.4] Exportar CSV ---")
    csv_path = _exportar_csv(df_alertas)

    log.info("--- [5.5] Notificacion SMTP ---")
    email_ok = _enviar_email(df_alertas, csv_path)

    log.info("=" * 60)
    log.info("RESUMEN MOTOR DE ALERTAS:")
    log.info("  SKUs analizados:   %d", len(df))
    log.info("  SKUs en alerta:    %d", len(df_alertas))
    log.info("  R4 ROJAS:         %d", r4_n)
    log.info("  R1 Quiebre:       %d", r1_n)
    log.info("  R5 AMARILLAS:     %d", r5_n)
    log.info("  R2 Sobre-stock:   %d", r2_n)
    log.info("  R3 Volatilidad:   %d", r3_n)
    log.info("  CSV: %s", csv_path)
    log.info("  Correo: %s", "Enviado" if email_ok else "No enviado (SMTP pendiente)")
    log.info("=" * 60)

    return {
        "total_alertas"  : len(df_alertas),
        "r4_rojo"        : int(r4_n),
        "r1_quiebre"     : int(r1_n),
        "r5_amarillo"    : int(r5_n),
        "r2_sobrestock"  : int(r2_n),
        "r3_volatilidad" : int(r3_n),
        "csv_path"       : str(csv_path),
        "email_enviado"  : email_ok,
    }


if __name__ == "__main__":
    try:
        res = run_alerts()
        print(f"\nAlertas: {res['total_alertas']} total")
        print(f"  🔴 R4 ROJA:      {res['r4_rojo']}")
        print(f"  🟠 R1 Quiebre:   {res['r1_quiebre']}")
        print(f"  🟡 R5 AMARILLA:  {res['r5_amarillo']}")
        print(f"  🔵 R2 Exceso:    {res['r2_sobrestock']}")
        print(f"  🟣 R3 Volat.:    {res['r3_volatilidad']}")
        print(f"  CSV: {res['csv_path']}")
        sys.exit(0)
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)
