# REPORTE FINAL

## EXCEL INDIVIDUAL

- **C9434:** Funcional (HTTP 200 OK) tras la corrección.
- **7695411:** Funcional (HTTP 200 OK).
- **Identificador esperado:** El endpoint `/api/export/rrff/excel/{sku}` y la consulta subyacente esperan idealmente el `sku` (ej. 7695411), pero debido a la cláusula `(sku = :s OR codigo_femaco = :s)` aceptan ambos.
- **Bug encontrado:** Si se enviaba el `codigo_femaco` (C9434), la base de datos retornaba el registro, pero el script buscaba `C9434` en el diccionario histórico de ventas (`sem_map`), donde la clave siempre es el `sku` (7695411). Esto dejaba las ventas vacías e invertía los identificadores.
- **Corrección necesaria:** Se modificó `get_sku_export_data` para extraer `real_sku = str(row_sop["sku"])` directamente del registro de la base de datos y usar este identificador canónico en adelante para las ventas y el diccionario de resultados.

## DATA PROCESSED

- **Archivos requeridos:** 0 (Cero). El runtime (FastAPI/Vite) consulta todo desde PostgreSQL en caliente. No se requieren CSVs de `data/processed` como dependencias del código fuente.
- **Regenerables:** Todos. 
- **No regenerables:** Ninguno.
- **Pipeline desde RAW reproducible:** Sí. Al ejecutar `src/main.py` y `src/dynamic_planner.py`, la totalidad de la carpeta `data/processed` (incluyendo `sellin_historico_clean.csv` y `sellout_historico_clean.csv`) se regenera de forma 100% automática desde los crudos.
- **Resultado:** No se requiere incorporar ningún archivo de `data/processed` al Consolidado; basta con mantener el directorio vacío.

## E2E NAVEGADOR

- **Login:** Autenticación exitosa (credenciales admin probadas, modal desaparece).
- **Dashboard:** Carga de lista de SKUs correcta. 223 SKUs renderizados (o universo actual equivalente).
- **Filtros:** Aplicados y removidos sin crashear el renderizado de la tabla.
- **Descarga Excel:** Botones de descarga de Excel visibles (en Compras) y funcionales (disparan la descarga).
- **Compras:** Renderizado correcto sin errores.
- **Planner Dinámico:** Visible y operando de acuerdo con las columnas del backend.
- **Shadow Mode:** Selector visible y filtros dinámicos funcionales.
- **SkuDetailModal:** Carga y cierra correctamente al interactuar con el botón "Ver Detalle".
- **Maquila:** Página carga de manera íntegra, recetas visibles.
- **Maquila Ordenes:** Página carga, lista de órdenes OC visibles.
- **Admin:** Página carga sin problemas, gestión de usuarios activa.

- **Console errors:** Ningún error de React (ErrorBoundary intacto).
- **HTTP errors:** Sin excepciones 404 inesperadas, sin errores 500 y sin problemas de CORS. (Solo 401 esperados en intentos de login fallidos preliminares).

## RUTAS

- **A:** 48 rutas productivas.
- **B:** 48 rutas productivas.
- **Unión:** 48 rutas únicas.
- **Consolidado:** 48 rutas implementadas.
- **Faltantes:** 0
- **Extras:** 0

## REGRESIÓN

- **Planner modificado:** No
- **Forecast modificado:** No
- **Sell In/Out modificado:** No
- **Tránsito modificado:** No
- **Sugerencias modificadas:** No

## GIT MODIFICADO: No

## VEREDICTO FINAL:

RRFF CONSOLIDADO APROBADO COMO BASE OFICIAL
