"""DAG diario del pipeline ETL de DataMart S.A.S.

Extrae dos CSV (volcado diario `data.csv` e historial `online_retail_II.csv`), los limpia y unifica
aplicando las reglas de negocio, valida la calidad y carga el warehouse PostgreSQL (esquema `dw`).

Idempotente: la carga es una transacción TRUNCATE + COPY + recálculo de agregados; ejecutarlo dos
veces con los mismos archivos deja exactamente el mismo contenido (docs/DECISIONES_TECNICAS.md §5).

Variables: datamart_products_api_url (opcional), datamart_raw_data_dir, datamart_work_dir, datamart_sales_file, datamart_history_file,
           datamart_source_timezone, datamart_max_reject_ratio
Connection: datamart_warehouse (PostgreSQL del repositorio analítico)
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from datamart_etl import tasks as etl
from datamart_etl.schemas import HISTORY, SALES_DAILY

default_args = {
    "owner": "ingenieria-de-datos",
    "retries": 3,  # reintentos automáticos ante fallos transitorios (BD no lista, archivo en escritura)
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="datamart_daily_etl",
    description="ETL diario DataMart: CSV de ventas + historial -> warehouse PostgreSQL",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # las tareas comparten el directorio de trabajo: una corrida a la vez
    default_args=default_args,
    tags=["datamart", "etl"],
    doc_md=__doc__,
) as dag:
    crear_esquema = PythonOperator(
        task_id="crear_esquema_warehouse",
        python_callable=etl.crear_esquema_warehouse,
    )
    extraer_ventas = PythonOperator(
        task_id="extraer_ventas_diarias_data_csv",
        python_callable=etl.extraer_fuente,
        op_kwargs={"system": SALES_DAILY.system},
    )
    extraer_historial = PythonOperator(
        task_id="extraer_historial_online_retail_ii",
        python_callable=etl.extraer_fuente,
        op_kwargs={"system": HISTORY.system},
    )
    enriquecer_categorias = PythonOperator(
        task_id="enriquecer_categorias_api_productos",
        python_callable=etl.enriquecer_categorias_api,
    )
    transformar = PythonOperator(
        task_id="transformar_y_unificar_fuentes",
        python_callable=etl.transformar_y_unificar,
    )
    validar_calidad = PythonOperator(
        task_id="validar_calidad_pre_carga",
        python_callable=etl.validar_calidad_pre_carga,
    )
    cargar = PythonOperator(
        task_id="cargar_warehouse",
        python_callable=etl.cargar_warehouse,
        op_kwargs={"logical_date": "{{ ds }}"},
    )
    validar_carga = PythonOperator(
        task_id="validar_carga_warehouse",
        python_callable=etl.validar_carga_warehouse,
    )

    crear_esquema >> [extraer_ventas, extraer_historial, enriquecer_categorias] >> transformar
    transformar >> validar_calidad >> cargar >> validar_carga
