import time
import schedule
import logging
from datetime import datetime
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SCHEDULER] %(message)s")
log = logging.getLogger("scheduler")

def run_pipeline():
    log.info("Iniciando ejecucion automatica del pipeline completo...")
    try:
        # Ejecuta el main.py usando el mismo ejecutable de Python de este entorno
        import sys
        subprocess.run([sys.executable, str(BASE_DIR / "src" / "main.py")], check=True)
        log.info("Ejecucion completada con exito.")
    except subprocess.CalledProcessError as e:
        log.error("El pipeline fallo: %s", e)
    except Exception as e:
        log.error("Error inesperado al ejecutar el pipeline: %s", e)

# 1. Ventas Semanales todos los lunes en la madrugada (03:00 AM)
schedule.every().monday.at("03:00").do(run_pipeline)

# 2. Históricos cada cambio de mes.
# Lo revisamos todos los días a las 04:00 AM; si es el día 1, ejecutamos.
def run_monthly_pipeline():
    if datetime.now().day == 1:
        log.info("Es el primer dia del mes. Ejecutando pipeline para actualizar historicos...")
        run_pipeline()

schedule.every().day.at("04:00").do(run_monthly_pipeline)

if __name__ == "__main__":
    log.info("="*60)
    log.info("Iniciando RRFF Scheduler Automatizado...")
    log.info(" - Tareas Semanales: Lunes 03:00 AM")
    log.info(" - Tareas Mensuales: Dia 1 del mes 04:00 AM")
    log.info("="*60)
    
    # Mantener el script corriendo en background
    while True:
        schedule.run_pending()
        time.sleep(60)
