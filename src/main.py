"""
main.py — Orquestador RRFF Soft
================================
Pipeline de procesamiento de datos de inteligencia comercial.

FASES:
  1. Extracción       → extractor.py          (Playwright → Shinyapps)
  2. Transformación   → transformer.py        (Maestro + Ventas + Inventario + OC Tránsito)
  3. Carga            → loader.py             (dim_productos | fact_ventas | fact_transito)
  4. Inteligencia SOP → planner.py            (Proyección 12m, YoY, Picos, UMP)
  5. Motor de Alertas → alerts.py             (R4-ROJA, R1-Quiebre, R5-AMARILLA, R2, R3 + SMTP)
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Aseguramos que /src esté en el path para imports relativos al ejecutar desde raíz
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Importar módulos de cada fase ─────────────────────────────────────────────
from extractor   import run_extraction      # Fase 1
from transformer import run_transformation  # Fase 2
from loader      import run_loading         # Fase 3
from planner     import run_planning        # Fase 4
from alerts      import run_alerts          # Fase 5

# ──────────────────────────────────────────────────────────────────────────────
# Configuración de logging del orquestador
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ORQUESTADOR] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")


def main():
    """Punto de entrada del pipeline RRFF Soft."""
    load_dotenv()

    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║      RRFF SOFT — Pipeline de Datos v4.0                ║")
    log.info("╚══════════════════════════════════════════════════════════╝")

    # ── FASE 1: Extracción ────────────────────────────────────────────────────
    log.info("▶  FASE 1 — Extracción de datos (Shinyapps)")
    try:
        archivos_raw = run_extraction()
        log.info("✔  FASE 1 completada. Archivos en /data/raw:")
        for nombre, ruta in archivos_raw.items():
            log.info("     • %s  (%s bytes)", nombre, ruta.stat().st_size)
    except Exception as exc:
        log.error("✘  FASE 1 falló: %s", exc)
        log.error("El pipeline se detiene. Revisa los logs del extractor.")
        sys.exit(1)

    # ── FASE 2: Transformación ────────────────────────────────────────────────
    log.info("FASE 2 - Transformacion y limpieza (Pandas)")
    try:
        archivos_proc = run_transformation(archivos_raw)
        log.info("FASE 2 completada. Archivos en /data/processed:")
        for nombre, ruta in archivos_proc.items():
            log.info("     - %s  (%s bytes)", nombre, ruta.stat().st_size)
    except Exception as exc:
        log.error("FASE 2 fallo: %s", exc)
        log.error("El pipeline se detiene. Revisa los logs del transformer.")
        sys.exit(1)

    # ── FASE 3: Carga a PostgreSQL ────────────────────────────────────────────
    log.info("FASE 3 - Carga a base de datos (PostgreSQL)")
    try:
        tablas = run_loading(archivos_proc)
        log.info("FASE 3 completada. Tablas en RRFF_AS_db:")
        for tabla, filas in tablas.items():
            log.info("     - %-20s  %d filas", tabla, filas)
    except Exception as exc:
        log.error("FASE 3 fallo: %s", exc)
        log.error("El pipeline se detiene. Revisa los logs del loader.")
        sys.exit(1)

    # ── FASE 4: Inteligencia SOP ──────────────────────────────────────────
    log.info("FASE 4 - Modulo de Inteligencia SOP (Proyecciones + YoY + UMP)")
    try:
        resultado_sop = run_planning(tablas)
        log.info("FASE 4 completada:")
        log.info("     - Tabla:    %s", resultado_sop["tabla"])
        log.info("     - Filas:    %d", resultado_sop["filas"])
        log.info("     - Columnas: %d", resultado_sop["columnas"])
    except Exception as exc:
        log.error("FASE 4 fallo: %s", exc)
        log.error("El pipeline se detiene. Revisa los logs del planner.")
        sys.exit(1)

    # ── FASE 5: Motor de Alertas con Tránsito ───────────────────────────────────
    log.info("FASE 5 - Motor de Alertas con Transito (R4-ROJA, R1, R5-AMARILLA, R2, R3)")
    try:
        res_alertas = run_alerts(resultado_sop)
        log.info("FASE 5 completada:")
        log.info("     - TOTAL alertas:    %d", res_alertas["total_alertas"])
        log.info("     - R4 ROJA:          %d", res_alertas.get("r4_rojo", 0))
        log.info("     - R1 Quiebre:       %d", res_alertas.get("r1_quiebre", 0))
        log.info("     - R5 AMARILLA:      %d", res_alertas.get("r5_amarillo", 0))
        log.info("     - R2 Sobre-stock:   %d", res_alertas.get("r2_sobrestock", 0))
        log.info("     - R3 Volatilidad:   %d", res_alertas.get("r3_volatilidad", 0))
        log.info("     - CSV: %s",              res_alertas["csv_path"])
        log.info("     - Email: %s",
                 "Enviado" if res_alertas["email_enviado"] else "No enviado (SMTP pendiente)")
    except Exception as exc:
        log.error("FASE 5 fallo: %s", exc)
        log.error("El pipeline se detiene. Revisa los logs del motor de alertas.")
        sys.exit(1)

    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║   Pipeline RRFF Soft v4.0 completado exitosamente           ║")
    log.info("║   Extraccion | Transform+Transito | Carga | SOP | Alertas  ║")
    log.info("╚══════════════════════════════════════════════════════════╝")



if __name__ == "__main__":
    main()
