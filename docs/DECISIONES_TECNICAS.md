# Decisiones técnicas

## 1. Arquitectura
Airflow 2.11.2 (LocalExecutor) en Docker, dos PostgreSQL 16 separados (metadatos y analítico). Se eligió la
rama 2.x porque el enunciado habla de "webserver"; Airflow 3 lo reemplaza por `api-server`. Detalle y patrón de
compose: <https://airflow.apache.org/docs/apache-airflow/2.11.2/howto/docker-compose/index.html>. Las dependencias se
instalan sobre la imagen oficial con el archivo de *constraints* de Airflow
(<https://airflow.apache.org/docs/docker-stack/build.html>).
Connection y Variables se registran al iniciar con `scripts/init_airflow.sh` (CLI de Airflow) para que
aparezcan en la UI; los valores salen de `.env`, ninguna credencial está en el código.

## 2. Casos ambiguos (sección 5 del enunciado)
| Caso | Decisión | Por qué / impacto |
|---|---|---|
| **Sin customer ID** | Se INCLUYEN con `customer_id` NULL y `is_anonymous = true` | Son ~25 % de las filas y 15 % del revenue; excluirlas subestimaría ventas. No se inventa un id (inflaría el conteo de clientes). Q5 mide la diferencia: ticket £998 vs £470 y devoluciones 12,2 % vs 6,2 % |
| **Descripciones variantes** | Nombre canónico = texto normalizado (mayúsculas, espacios colapsados) más frecuente entre las VENTAS del código; desempate: apariciones totales y luego orden alfabético. Se guardan todas las variantes | Elegir por ventas evita que notas de ajuste ("DAMAGED", "?") ganen. Mayúsculas/espacios no cuentan como inconsistencia; sí cuentan nombres distintos |
| **Duplicados entre fuentes** | Clave compuesta (factura, producto, instante UTC, cantidad, precio, cliente, país); si coincide, **gana data.csv** | data.csv es el volcado operativo vigente; el historial se usa para lo que data.csv no cubre. Medido: 535.463 filas solapadas (el 100 % de data.csv) |
| **Duplicados dentro de una fuente** | Filas idénticas en todas las columnas: se conserva la primera y las demás van a `rejected_records` (`DUPLICADO_EXACTO_EN_FUENTE`) | Es el criterio habitual en este dataset. Riesgo: podría ser el mismo ítem escaneado dos veces; el impacto es 5.265 + 34.213 filas, visible y reversible |
| **Códigos no estándar** | Normalizados a mayúsculas sin espacios. `POST, DOT, M, C2, D, S, B, BANKCHARGES, AMAZONFEE, CRUK, ADJUST*, TEST*, GIFT_*` = `NO_PRODUCTO` (se cargan, pero excluidos de rankings de productos); `DCGS*`, `PADS` = mercancía con patrón `ALTERNO` | Siguen siendo ingreso real (fletes, comisiones) pero no son referencias de catálogo |
| **Cantidad <= 0** | `fact_returns`: `DEVOLUCION` si la factura empieza por "C", `AJUSTE` si no | Separa devolución comercial de ajuste de inventario |
| **Precio <= 0** | En venta (cantidad > 0): se rechaza (`PRECIO_NO_POSITIVO_EN_VENTA`). En ajuste con precio 0: se conserva con importe 0. Precio negativo en ajuste: se rechaza | La regla del enunciado aplica a ventas; un ajuste sin valor mueve unidades, no dinero |
| **Fechas** | Hora local `Europe/London` (Variable `datamart_source_timezone`) -> UTC. Hora ambigua: horario de verano; inexistente: se adelanta | Las fuentes no traen zona; la tienda es del Reino Unido. Verificado: el 100 % de las filas de data.csv coinciden con el historial tras convertir |
| **Países** | EIRE -> Ireland, RSA -> South Africa, USA -> United States; vacío -> Unspecified | Nombres legibles |
| **Moneda** | No hay conversión: todos los importes están en libras (GBP) en ambas fuentes | El enunciado habla de varias monedas, pero estos datasets no las traen |

Si varias reglas de rechazo aplican a una fila, se guarda un solo motivo (el primero de la lista en `schemas.py`).

## 3. Categorías: API de productos (plus 4.3) con reglas de respaldo
La API existe (`api/`, ver `docs/API_PRODUCTOS.md`) y la tarea `enriquecer_categorias_api_productos` descarga su catálogo
antes de transformar. Una categoría de la API manda sobre las reglas (`category_source = api`), salvo las que la propia
API marcó como `default`. Con la Variable `datamart_products_api_url` vacía el pipeline funciona igual, solo con reglas.
Las reglas funcionan así: palabras clave de palabras clave sobre el nombre canónico (`include/datamart_etl/reference/category_rules.csv`),
con prioridades (los overrides específicos como "PAPER CHAIN" -> Hogar van primero). Lo que no coincide cae en
**Hogar por defecto** y queda marcado `category_source = default`. Limitación: ~83 % del revenue cae en el
valor por defecto (el catálogo real es decoración y regalos, no las 5 categorías del enunciado). Los análisis por
categoría (Q2) deben leerse con esa salvedad. `assign_categories` es el punto de enchufe para la API.

## 4. Idempotencia
Cada corrida hace, en UNA transacción, `TRUNCATE ... RESTART IDENTITY` + `COPY` + recálculo de agregados.
Los DataFrames se ordenan de forma determinista, así que hasta los ids generados son iguales. Si algo falla,
PostgreSQL revierte y queda el estado anterior (probado en `tests/test_warehouse_integration.py`).
`etl_run_audit` usa clave (fecha lógica, fuente, métrica) con UPSERT. Comprobación:
`sql/checks/table_checksums.sql` antes y después de re-ejecutar; las 9 huellas fueron idénticas.
Costo: el TRUNCATE bloquea lecturas durante la carga (segundos) y reprocesa todo el archivo cada día.

## 5. Calidad y reintentos
`validar_calidad_pre_carga` falla SIN reintentar (`AirflowFailException`) si hay precios <= 0 en ventas, códigos sin
normalizar, fechas fuera de UTC, duplicados, llaves huérfanas, filas que no concilian o una fuente supera
`datamart_max_reject_ratio` (5 %). Los fallos transitorios sí se reintentan (3 veces, retroceso exponencial).
`validar_carga_warehouse` concilia conteos e importes del warehouse contra la transformación.

## 6. Pendiente / limitaciones honestas
- **Entorno Docker sin ejecutar por mí.** El DAG se ejecutó de punta a punta con Airflow 2.11.2 y PostgreSQL 16
  reales, pero fuera de Docker (no había Docker disponible). `docker-compose.yml`, `Dockerfile` e `init_airflow.sh`
  se validaron como YAML y contra el compose oficial; el primer `docker-compose up` real es la prueba pendiente.
- **API de productos (4.3):** implementada, pero su catálogo se deriva de `Sales Transaction v.4a.csv` con las mismas reglas
  de palabras clave, así que no aporta información de categoría nueva (solo demuestra la integración). No trae país del proveedor.
  **No se ejecutó dentro de Docker ni en Airflow real en esta revisión** (se probó la API con uvicorn y las funciones con pytest).
- **Carga incremental:** hoy es refresco completo. Para volúmenes mayores: particionar los hechos por mes y hacer
  `MERGE` por clave natural solo de la ventana nueva.
- **Historial usado:** Online Retail II de UCI como fuente 4.2; si tu `online_retail_II.csv` de Kaggle difiere, el lector
  tolera alias de columnas y 3 formatos de fecha; otro formato se rechaza como `FECHA_INVALIDA`.
- **Tasas de devolución > 100 %** (Q3b) son anomalías de datos (la venta original no está en el periodo o tiene otro código).
