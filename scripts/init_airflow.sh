#!/usr/bin/env bash
# Corre dentro del servicio airflow-init, después de migrar la BD y crear el usuario admin.
# Deja registradas la Connection y las Variables que necesita el DAG, sin pasar por la UI.
# Es idempotente: se puede ejecutar cuantas veces se quiera (docker-compose up repite el init).
set -euo pipefail

echo "[init] Connection datamart_warehouse -> ${WAREHOUSE_DB_HOST}:${WAREHOUSE_DB_PORT}/${WAREHOUSE_DB_NAME}"
airflow connections delete datamart_warehouse >/dev/null 2>&1 || true
airflow connections add datamart_warehouse \
  --conn-type postgres \
  --conn-host "${WAREHOUSE_DB_HOST}" \
  --conn-port "${WAREHOUSE_DB_PORT}" \
  --conn-schema "${WAREHOUSE_DB_NAME}" \
  --conn-login "${WAREHOUSE_DB_USER}" \
  --conn-password "${WAREHOUSE_DB_PASSWORD}"

echo "[init] Variables operativas"
airflow variables set datamart_raw_data_dir       "/opt/airflow/data/raw"
airflow variables set datamart_work_dir           "/opt/airflow/data/work"
airflow variables set datamart_sales_file         "${DATAMART_SALES_FILE}"
airflow variables set datamart_history_file       "${DATAMART_HISTORY_FILE}"
airflow variables set datamart_source_timezone    "${DATAMART_SOURCE_TIMEZONE}"
airflow variables set datamart_max_reject_ratio   "${DATAMART_MAX_REJECT_RATIO}"
airflow variables set datamart_products_api_url   "${DATAMART_PRODUCTS_API_URL:-}"

echo "[init] Probando la Connection (no bloquea el arranque si falla)"
airflow connections test datamart_warehouse || echo "[init] AVISO: la prueba de conexión falló; revisa credenciales del warehouse"

echo "[init] Listo."
