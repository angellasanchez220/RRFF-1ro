"""
extractor.py — Motor de Extracción RRFF Soft
=============================================
Fase 1 del orquestador: autentica en femaco.shinyapps.io/matrix y descarga
los tres reportes críticos hacia /data/raw:

  1. maestro_productos.csv    →  Módulo 7 (Bases de Datos / app Datos)
  2. ventas_semanales.csv     →  Módulo 3 (Ventas Semanales), modo = Unidades
  3. estado_inventario.csv    →  Módulo 7 (Bases de Datos / app Datos), Stock HC

Dependencias: playwright, python-dotenv
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR         = Path(__file__).resolve().parent.parent
RAW_DIR          = BASE_DIR / "data" / "raw"
MANUAL_UPLOADS   = BASE_DIR / "data" / "manual_uploads"

# Crear directorios si no existen
RAW_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_UPLOADS.mkdir(parents=True, exist_ok=True)

# URL principal del portal Matrix
load_dotenv()
MATRIX_URL = os.getenv("MATRIX_URL", "https://conexos-femaco-matrix.share.connect.posit.cloud/").strip().strip('"')

# ── Selectores del Módulo 3 — Ventas Semanales ────────────────────────────────
# Radio group "Visualización de valores": name="modo", values=["Ventas","Unidades"]
SEL_RADIO_UNIDADES   = 'input[name="modo"][value="Unidades"]'
SEL_RADIO_VENTAS     = 'input[name="modo"][value="Ventas"]'
# Botón de descarga CSV de la DataTable (clase dt-button de DataTables)
SEL_BTN_CSV_DATATABLE = "button.buttons-csv"

# ── Selectores del Módulo 7 — Bases de Datos (app Datos) ─────────────────────
# Botón de descarga del Maestro de Productos (shiny-download-link)
SEL_BTN_DL_PRODUCTOS    = "#dl_productos"
# Botón de descarga del Estado de Inventario (Stock HC por tienda)
SEL_BTN_DL_INVENTARIO   = "#dl_stock_hist\u00f3rico"

# Timeouts (ms)
TIMEOUT_NAV = 90_000    # carga inicial / navegación
TIMEOUT_UI  = 60_000    # aparición de elementos en DOM
TIMEOUT_DL  = 300_000   # espera de evento download

# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXTRACTOR] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("extractor")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _load_credentials() -> tuple[str, str]:
    """Carga y valida MATRIX_USER y MATRIX_PWD desde el archivo .env."""
    load_dotenv()
    user = os.getenv("MATRIX_USER", "").strip().strip('"')
    pwd  = os.getenv("MATRIX_PWD",  "").strip().strip('"')
    if not user or not pwd:
        raise EnvironmentError(
            "MATRIX_USER o MATRIX_PWD no estan definidos en el archivo .env"
        )
    log.info("Credenciales cargadas — usuario: %s", user)
    return user, pwd


def _wait_for_shiny_ready(page, timeout: int = TIMEOUT_NAV) -> None:
    """
    Aguarda a que Shiny termine de renderizar y computar los datos.
    Estrategia:
      1. DOM cargado (domcontentloaded)
      2. Indicador .shiny-busy desaparece (Shiny termino su ciclo reactivo)
      3. Buffer de 5 s para que el servidor entregue datos a los outputs
    """
    log.info("Esperando ciclo reactivo de Shiny...")
    page.wait_for_load_state("domcontentloaded", timeout=timeout)

    # Overlay de desconexion (si aparece, algo salio mal)
    try:
        page.wait_for_selector(
            "#shiny-disconnected-overlay", state="detached", timeout=5_000
        )
    except PlaywrightTimeout:
        pass

    # Esperar que Shiny termine de procesar
    try:
        page.wait_for_selector(".shiny-busy", state="detached", timeout=30_000)
        log.info("Indicador .shiny-busy desaparecio — UI lista.")
    except PlaywrightTimeout:
        log.warning(".shiny-busy no detectado — asumiendo Shiny listo.")

    log.info("Buffer de 5 s para generacion de datos en el servidor...")
    page.wait_for_timeout(5_000)


def _validate_csv(path: Path) -> bool:
    """
    Verifica que el archivo descargado sea un CSV real y no una
    pagina HTML de Shiny (placeholder 'please wait').
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first_bytes = f.read(10).strip()
        return not first_bytes.startswith("<")
    except Exception:
        return False


def _select_radio(page, selector: str, label: str) -> None:
    """
    Localiza un radio button por selector CSS y lo activa con clic explicito.
    Hace scroll al elemento, verifica su estado y dispara el evento JS click.
    """
    log.info("Buscando control de seleccion: %s (%s)...", label, selector)
    try:
        page.wait_for_selector(selector, state="visible", timeout=TIMEOUT_UI)
    except PlaywrightTimeout:
        raise RuntimeError(
            f"Radio button '{label}' ({selector}) no encontrado o no visible."
        )

    radio = page.locator(selector)
    radio.scroll_into_view_if_needed(timeout=10_000)

    is_checked = radio.is_checked()
    if is_checked:
        log.info("Radio '%s' ya estaba seleccionado — sin cambios.", label)
        return

    log.info("Activando radio '%s'...", label)
    radio.evaluate("el => el.click()")

    # Confirmar que quedo seleccionado
    page.wait_for_timeout(500)
    if radio.is_checked():
        log.info("Radio '%s' activado correctamente.", label)
    else:
        log.warning("El radio '%s' no reflejo el cambio — se continua de todas formas.", label)

    # Dar tiempo a Shiny para que procese el cambio reactivo
    log.info("Esperando que Shiny procese el cambio de modo (3 s)...")
    page.wait_for_timeout(3_000)
    try:
        page.wait_for_selector(".shiny-busy", state="detached", timeout=20_000)
    except PlaywrightTimeout:
        pass


def _download_shiny_link(page, selector: str, dest_path: Path, label: str) -> Path:
    """
    Descarga via un elemento <a class='shiny-download-link'> de Shiny.
    Implementa reintentos con validacion CSV para evitar placeholders HTML.
    Uso: Maestro de Productos.
    """
    log.info("Descargando '%s' via shiny-download-link (%s)...", label, selector)

    try:
        page.wait_for_selector(selector, state="visible", timeout=TIMEOUT_UI)
    except PlaywrightTimeout:
        raise RuntimeError(f"Boton Shiny '{selector}' no encontrado o no visible.")

    element = page.locator(selector)
    element.scroll_into_view_if_needed(timeout=10_000)

    is_disabled = element.get_attribute("disabled")
    log.info("Estado del enlace '%s': %s", label,
             "DESHABILITADO" if is_disabled else "habilitado")

    for intento in range(1, 4):
        log.info("Intento %d/3 de descarga para '%s'...", intento, label)
        with page.expect_download(timeout=TIMEOUT_DL) as dl_info:
            element.evaluate("el => el.click()")

        dl = dl_info.value
        log.info("Archivo recibido del servidor: %s", dl.suggested_filename)
        dl.save_as(str(dest_path))

        if _validate_csv(dest_path):
            log.info("Guardado: %s  (%d bytes)", dest_path, dest_path.stat().st_size)
            return dest_path
        else:
            log.warning(
                "Intento %d: el archivo es HTML (servidor aun procesando). "
                "Esperando 15 s antes de reintentar...", intento
            )
            page.wait_for_timeout(15_000)
            element = page.locator(selector)

    raise RuntimeError(
        f"'{label}' no pudo descargarse como CSV tras 3 intentos."
    )


def _download_datatable_csv(page, dest_path: Path, label: str) -> Path:
    """
    Descarga via el boton CSV de una DataTable de DataTables.js.
    Selector: button.buttons-csv
    Uso: Ventas Semanales (el reporte se genera desde la vista reactiva).
    """
    log.info("Descargando '%s' via boton DataTable CSV...", label)

    try:
        page.wait_for_selector(SEL_BTN_CSV_DATATABLE, state="visible", timeout=TIMEOUT_UI)
    except PlaywrightTimeout:
        raise RuntimeError(
            f"Boton CSV de DataTable no encontrado. "
            f"Verifica que la tabla de '{label}' haya cargado."
        )

    btn = page.locator(SEL_BTN_CSV_DATATABLE).first
    btn.scroll_into_view_if_needed(timeout=10_000)

    # El boton CSV de DataTables genera la descarga al hacer clic
    log.info("Ejecutando clic en boton CSV de DataTable...")
    with page.expect_download(timeout=TIMEOUT_DL) as dl_info:
        btn.evaluate("el => el.click()")

    dl = dl_info.value
    log.info("Archivo recibido: %s", dl.suggested_filename)
    dl.save_as(str(dest_path))

    if _validate_csv(dest_path):
        log.info("Guardado: %s  (%d bytes)", dest_path, dest_path.stat().st_size)
        return dest_path
    else:
        raise RuntimeError(
            f"'{label}': el archivo descargado no es un CSV valido."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Sub-flujos por módulo
# ──────────────────────────────────────────────────────────────────────────────



def _extraer_maestro_y_stock(context, dashboard_page) -> tuple[Path, Path, Path, Path]:
    """
    FLUJO: Módulo 7 — Bases de Datos (una sola sesión, 4 descargas)
    ----------------------------------------------------------------
    1. Clic en btn_Modulo_7 → nueva pestaña (Datos_app)
    2. Esperar Shiny ready
    3. Descargar dl_productos via shiny-download-link → maestro_productos.csv
    4. Descargar dl_stock_histórico                   → estado_inventario.csv
    5. Descargar Sell Out Histórico                   → sellout_historico.csv
    6. Descargar Sell In Histórico                    → sellin_historico.csv
    Reutiliza la misma pestaña para todas las descargas (eficiencia).
    """
    dest_maestro    = RAW_DIR / "maestro_productos.csv"
    dest_inventario = RAW_DIR / "estado_inventario_hc.csv"
    dest_sellout    = RAW_DIR / "sellout_historico.csv"
    dest_sellin     = RAW_DIR / "sellin_historico.csv"

    log.info("--- Modulo 7: Maestro + Stock + SellOut Hist. + SellIn Hist. ---")
    log.info("Abriendo app de Bases de Datos...")
    with context.expect_page(timeout=TIMEOUT_UI) as new_page_info:
        dashboard_page.click("#btn_Modulo_7")

    datos_page = new_page_info.value
    log.info("Nueva pestana: %s", datos_page.url)

    datos_page.wait_for_load_state("load", timeout=TIMEOUT_NAV)
    _wait_for_shiny_ready(datos_page)
    log.info("App Datos lista.")

    # Descarga 1: Maestro de Productos
    path_maestro = _download_shiny_link(
        datos_page, SEL_BTN_DL_PRODUCTOS, dest_maestro, "Maestro de Productos"
    )

    # Descarga 2: Estado de Inventario (Stock HC)
    log.info("--- Descargando Estado de Inventario (Stock HC) ---")
    _wait_for_shiny_ready(datos_page)
    try:
        path_inventario = _download_shiny_link(
            datos_page, SEL_BTN_DL_INVENTARIO, dest_inventario, "Estado de Inventario"
        )
    except Exception as e:
        log.error("Fallo descarga Estado de Inventario: %s", e)
        path_inventario = None

    # Descarga 3: Sell Out Historico
    log.info("--- Descargando Sell Out Historico ---")
    _wait_for_shiny_ready(datos_page)
    path_sellout = _download_shiny_link(
        datos_page, "#dl_sell_out_histórico", dest_sellout, "Sell Out Histórico"
    )

    # Descarga 4: Sell In Historico
    log.info("--- Descargando Sell In Historico ---")
    _wait_for_shiny_ready(datos_page)
    path_sellin = _download_shiny_link(
        datos_page, "#dl_sell_in_histórico", dest_sellin, "Sell In Histórico"
    )

    datos_page.close()
    return path_maestro, path_inventario, path_sellout, path_sellin


def _extraer_ventas_semanales(context, dashboard_page) -> Path:
    """
    FLUJO: Módulo 3 — Ventas Semanales (modo Unidades)
    ---------------------------------------------------
    1. Clic en btn_Modulo_3 → nueva pestaña (Ventas_semanales_app)
    2. Esperar Shiny ready
    3. REGLA CONDICIONAL: localizar radio[name="modo"] y seleccionar "Unidades"
       - Si ya esta en Unidades: no actuar
       - Si esta en Ventas (default): hacer clic explicito en Unidades y esperar
         que Shiny recompute la tabla reactiva
    4. Descargar via boton CSV de la DataTable
    """
    dest = RAW_DIR / "ventas_semanales.csv"

    log.info("--- Modulo 3: Ventas Semanales ---")
    log.info("Abriendo app de Ventas Semanales...")
    with context.expect_page(timeout=TIMEOUT_UI) as new_page_info:
        dashboard_page.click("#btn_Modulo_3")

    ventas_page = new_page_info.value
    log.info("Nueva pestana: %s", ventas_page.url)

    ventas_page.wait_for_load_state("load", timeout=TIMEOUT_NAV)
    _wait_for_shiny_ready(ventas_page)
    log.info("App Ventas Semanales lista.")

    # ── REGLA CONDICIONAL: Seleccionar modo "Unidades" ────────────────────────
    log.info("Aplicando regla de seleccion de parametro: modo = Unidades")
    _select_radio(ventas_page, SEL_RADIO_UNIDADES, "Unidades")
    # Esperar que Shiny termine de recomputar la tabla con los nuevos valores
    _wait_for_shiny_ready(ventas_page)
    log.info("Tabla recomputed en modo Unidades.")

    # ── Descargar CSV de la DataTable ─────────────────────────────────────────
    path = _download_datatable_csv(ventas_page, dest, "Ventas Semanales (Unidades)")
    ventas_page.close()
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Flujo principal
# ──────────────────────────────────────────────────────────────────────────────

def run_extraction() -> dict[str, Path]:
    """
    Ejecuta el pipeline completo de extraccion:
      Fase 1a: Autenticacion en Matrix
      Fase 1b: Maestro de Productos + Estado de Inventario  (Modulo 7)
      Fase 1c: Ventas Semanales      (Modulo 3 - modo Unidades)

    Retorna dict {nombre_csv: Path_destino}.
    """
    user, pwd = _load_credentials()
    resultados: dict[str, Path] = {}

    log.info("=" * 60)
    log.info("FASE 1 - Motor de Extraccion iniciado")
    log.info("Destino RAW:           %s", RAW_DIR)
    log.info("Destino Manual Uploads: %s", MANUAL_UPLOADS)
    log.info("Reportes en scope:     Maestro Productos | Estado Inventario (Stock HC) | Ventas Semanales")
    log.info("=" * 60)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page    = context.new_page()

        try:
            # ── PASO 1: Navegar al portal Matrix ──────────────────────────────
            log.info("Navegando a %s ...", MATRIX_URL)
            # Shinyapps mantiene WebSocket persistente → usar "load" no "networkidle"
            page.goto(MATRIX_URL, timeout=TIMEOUT_NAV, wait_until="load")

            # ── PASO 2: Autenticacion ─────────────────────────────────────────
            log.info("Completando formulario de login...")
            page.wait_for_selector("#auth-user_id", state="visible", timeout=TIMEOUT_NAV)
            page.fill("#auth-user_id", user)
            page.fill("#auth-user_pwd", pwd)
            page.click("#auth-go_auth")

            log.info("Autenticando... esperando dashboard principal...")
            try:
                page.wait_for_selector("#btn_Modulo_7", state="visible", timeout=TIMEOUT_NAV)
                log.info("Autenticacion exitosa.")
            except PlaywrightTimeout as e:
                log.error("Timeout esperando #btn_Modulo_7. Diagnosticando estado de la pagina...")
                
                # Crear dir de debug
                DEBUG_DIR = BASE_DIR / "data" / "debug"
                DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                
                # Registrar url y titulo
                log.error("URL actual: %s", page.url)
                log.error("Titulo: %s", page.title())
                
                # Guardar captura y HTML
                screenshot_path = DEBUG_DIR / "matrix_after_login.png"
                html_path = DEBUG_DIR / "matrix_after_login.html"
                
                page.screenshot(path=str(screenshot_path))
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                    
                log.error("Captura guardada en: %s", screenshot_path)
                log.error("HTML guardado en: %s", html_path)
                
                # Detectar mensajes de error visibles si los hay
                error_msgs = page.locator(".shiny-output-error, .alert-danger, #auth-error").all_inner_texts()
                if error_msgs:
                    log.error("Mensajes de error detectados: %s", error_msgs)
                else:
                    log.error("No se detectaron contenedores de error estandar.")
                
                raise
            # ── PASO 3: Modulo 7 (Maestro, SellOut Hist, SellIn Hist) ──
            try:
                p_maestro, p_stock, p_sellout, p_sellin = _extraer_maestro_y_stock(context, page)
                resultados["maestro_productos.csv"] = p_maestro
                resultados["estado_inventario_hc.csv"] = p_stock
                resultados["sellout_historico.csv"] = p_sellout
                resultados["sellin_historico.csv"]  = p_sellin
            except Exception as exc:
                log.error("Error en Modulo 7: %s", exc)
                resultados["maestro_productos.csv"] = None
                resultados["estado_inventario_hc.csv"] = None
                resultados["sellout_historico.csv"] = None
                resultados["sellin_historico.csv"]  = None

            # ── PASO 4: Ventas Semanales en Unidades (Modulo 3) ───────────────
            try:
                path_ventas = _extraer_ventas_semanales(context, page)
                resultados["ventas_semanales.csv"] = path_ventas
            except Exception as exc:
                log.error("Error en Ventas Semanales: %s", exc)
                resultados["ventas_semanales.csv"] = None

        except PlaywrightTimeout as e:
            log.error("Timeout de Playwright: %s", e)
            raise
        except Exception as e:
            log.error("Error inesperado en el flujo de extraccion: %s", e)
            raise
        finally:
            context.close()
            browser.close()

    # ── Resumen ───────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("RESUMEN DE EXTRACCION:")
    exitos   = [k for k, v in resultados.items() if v is not None]
    fallidos = [k for k, v in resultados.items() if v is None]
    for nombre in exitos:
        log.info("  OK  %s", nombre)
    for nombre in fallidos:
        log.warning("  FALLO  %s", nombre)
    log.info("Total: %d/%d reportes descargados.", len(exitos), len(resultados))
    log.info("=" * 60)

    if fallidos:
        raise RuntimeError(
            f"Los siguientes reportes no pudieron descargarse: {fallidos}"
        )

    return resultados


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada standalone
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        archivos = run_extraction()
        print("\nArchivos descargados exitosamente:")
        for nombre, ruta in archivos.items():
            print(f"  - {nombre}  ->  {ruta}")
        sys.exit(0)
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)
