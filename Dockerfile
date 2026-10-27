# Imagen oficial de Airflow + las dependencias del ETL, instaladas con el archivo de
# constraints oficial de Airflow para no romper el resolvedor de versiones.
# Fuente: https://airflow.apache.org/docs/docker-stack/build.html#adding-new-pypi-packages
FROM apache/airflow:2.11.2-python3.12

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.11.2/constraints-3.12.txt"
