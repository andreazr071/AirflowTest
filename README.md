# DataMart S.A.S. — Pipeline ETL con Apache Airflow y Data Warehouse

CSV de ventas (`data.csv`) + historial (`online_retail_II.csv`) -> limpieza y reglas de negocio -> PostgreSQL
analítico (esquema `dw`), todo orquestado por un DAG diario de Airflow 2.11.2 dentro de Docker.

## Inicio rápido (menos de 10 minutos)
Requisitos: Docker con Compose y **al menos 4 GB de RAM** asignados a Docker.

```bash
git clone <URL-del-repositorio> datamart-etl && cd datamart-etl
cp .env.example .env            # cambia las contraseñas; en Linux pon AIRFLOW_UID=$(id -u)
```
**Datos** (elige una opción):
- *Prueba rápida (1 min):* en `.env` deja `RAW_DATA_DIR=./data/seeds` (muestras reales ya incluidas).
- *Carga completa:* copia `data.csv` (Kaggle `carrie1/ecommerce-data`) y `online_retail_II.csv` a `data/raw/`
  (el segundo es opcional: si no existe, el pipeline lo omite con un aviso y sigue).

```bash
docker-compose up --build       # (o: docker compose up --build)  primera vez: 3 a 5 minutos
```
Al terminar el arranque: UI en <http://localhost:8080> (o el puerto de `AIRFLOW_WEBSERVER_PORT` en tu `.env`) (usuario y clave = `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` de tu `.env`).
El DAG `datamart_daily_etl` arranca solo (no está en pausa). Con los CSV completos tarda ~2 minutos.

## Verificación paso a paso
| Requisito | Cómo comprobarlo |
|---|---|
| Un solo comando levanta todo | `docker-compose ps`: 4 servicios en `running`/`healthy` y `airflow-init` en `exited (0)` |
| Webserver con admin creado | Abrir <http://localhost:8080> e iniciar sesión |
| Scheduler | `docker-compose ps` (healthy) y el DAG aparece y corre en la UI |
| BD de metadatos separada de la analítica | `docker-compose ps`: `airflow-metadata-db` y `warehouse-db` son servicios distintos con bases y usuarios distintos |
| Tablas creadas al iniciar | `docker-compose exec warehouse-db psql -U <WAREHOUSE_DB_USER> -d <WAREHOUSE_DB_NAME> -c '\dt dw.*'` (9 tablas, aun antes de correr el DAG) |
| Connection | UI: Admin -> Connections -> `datamart_warehouse`; o `docker-compose exec airflow-webserver airflow connections get datamart_warehouse` |
| Variables | UI: Admin -> Variables (6 `datamart_*`); o `docker-compose exec airflow-webserver airflow variables list` |
| Secretos fuera del código | `git grep -i password` solo muestra nombres de variables; `.env` está en `.gitignore` |
| DAG con tareas, dependencias y reintentos | UI -> DAG -> Graph (8 tareas); `retries=3` en `dags/datamart_daily_etl.py` |
| Datos llegaron al warehouse | ver abajo |
| Idempotencia | ver abajo |
| Preguntas de negocio | `sql/queries/Q1..Q7*.sql` |
| API de productos (plus 4.3) | <http://localhost:8000/docs> y `curl "http://localhost:8000/products?page=1&page_size=5"` (ver `docs/API_PRODUCTOS.md`) |

### Ver que los datos llegaron
Conéctate con cualquier cliente a `localhost:<WAREHOUSE_HOST_PORT>` (por defecto 5433) con el usuario y base de tu `.env`, o:
```bash
docker-compose exec warehouse-db psql -U "$WAREHOUSE_DB_USER" -d "$WAREHOUSE_DB_NAME" \
  -c "SELECT (SELECT count(*) FROM dw.fact_sales) ventas, (SELECT count(*) FROM dw.fact_returns) devoluciones, (SELECT count(*) FROM dw.rejected_records) rechazos"
```
Con los CSV completos (data.csv + Online Retail II) se esperan **1.007.912 ventas, 22.496 devoluciones/ajustes y 43.409 rechazos**. Solo con data.csv: 524.876 / 10.587 / 6.446.
Para ejecutar una consulta: `docker-compose exec -T warehouse-db psql -U ... -d ... < sql/queries/Q1_ventas_netas_mensuales.sql`.

### Probar la idempotencia
```bash
docker-compose exec -T warehouse-db psql -U ... -d ... < sql/checks/table_checksums.sql > antes.txt
docker-compose exec airflow-webserver airflow dags test datamart_daily_etl 2026-01-01   # o "Trigger DAG" en la UI
docker-compose exec -T warehouse-db psql -U ... -d ... < sql/checks/table_checksums.sql > despues.txt
diff antes.txt despues.txt && echo "IDEMPOTENTE"
```
(Si lo haces con una fecha lógica distinta, `etl_run_audit` guarda una fecha más y su huella cambia; las otras 8 tablas deben coincidir.)

## Estructura
```
docker-compose.yml · Dockerfile · .env.example · requirements*.txt
dags/datamart_daily_etl.py          DAG (solo orquestación)
api/                                API REST de productos (FastAPI) + catálogo CSV + pruebas
include/datamart_etl/               schemas · transform · categories · quality · warehouse · tasks
include/datamart_etl/reference/     category_rules.csv
sql/ddl/001_schema.sql              DDL (se ejecuta al crear el contenedor y desde el DAG)
sql/refresh_aggregates.sql          neto diario por producto
sql/queries/Q1..Q7                  consultas de las preguntas de negocio
sql/checks/table_checksums.sql      huellas para idempotencia
scripts/                            init_airflow.sh (Connection + Variables) · profile_sources.py
data/seeds/                         muestras reales; data/raw/ = CSV completos (no versionados)
docs/                               API_PRODUCTOS · DECISIONES_TECNICAS · MODELO_DATOS (+ .dbml) · EXPLORACION_DATOS · RECOMENDACION_PRODUCTO
tests/                              unitarias + integración
```

## Pruebas
```bash
python -m venv .venv && . .venv/bin/activate
pip install apache-airflow[postgres]==2.11.2 pandas pyarrow pytest \
  --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.11.2/constraints-3.12.txt
python -m pytest tests -q                                   # 21 unitarias (las 2 de integración se omiten)
WAREHOUSE_TEST_DSN="host=localhost port=5433 dbname=<base_de_prueba> user=... password=..." python -m pytest tests -q
```
**Cuidado:** la prueba de integración VACÍA las tablas `dw` de la base que apuntes; usa una base de pruebas.

## Problemas frecuentes
- *El DAG falla en `extraer_*`:* falta el CSV en `RAW_DATA_DIR`.
- *Cambié el DDL y no se aplica:* el init de Postgres solo corre con volumen vacío; el DAG reaplica el DDL (`CREATE ... IF NOT EXISTS`) pero no migra tablas existentes. Reinicio total: `docker-compose down -v`.
- *Permisos en `logs/` o `data/work/` (Linux):* pon `AIRFLOW_UID=$(id -u)` en `.env`.

Decisiones, casos ambiguos y pendientes: [`docs/DECISIONES_TECNICAS.md`](docs/DECISIONES_TECNICAS.md).
