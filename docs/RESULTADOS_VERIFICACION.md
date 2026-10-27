# Qué se verificó y cómo

Entorno de verificación: Airflow 2.11.2 y PostgreSQL 16 reales (instalados fuera de Docker, con pandas 2.1.4 y
pyarrow 22 = versiones del constraints de Airflow 2.11.2), datos: `data.csv` + Online Retail II (UCI).

| Verificado | Resultado |
|---|---|
| DAG se importa sin errores; 7 tareas y dependencias según diseño | OK |
| `airflow dags test` de punta a punta (≈ 80 s con 1,6 M de filas) | 7/7 `SUCCESS` |
| Corrida solo con `data.csv` (fuente de historial omitida) | 524.876 ventas, 10.587 devoluciones/ajustes, 6.446 rechazos |
| Corrida con ambas fuentes | 1.007.912 ventas, 22.496 devoluciones/ajustes, 43.409 rechazos, 535.463 descartadas por solapamiento |
| Idempotencia (misma fecha, dos corridas) | 9/9 huellas md5 idénticas (`sql/checks/table_checksums.sql`) |
| Umbral de rechazo superado / archivo requerido ausente | La tarea falla sin reintentar y el warehouse no cambia |
| Carga fallida a mitad (CHECK violado) | Rollback: el warehouse conserva el estado previo (`tests/test_warehouse_integration.py`) |
| Pruebas | 21 unitarias + 2 de integración pasan; 3 mutaciones manuales detectadas |
| Consultas Q1 a Q7 | Ejecutadas contra el warehouse cargado |

**NO verificado:** `docker-compose up`, el `Dockerfile` y `scripts/init_airflow.sh` (Docker no estaba disponible).
Están validados como YAML y alineados con el compose oficial de Airflow 2.11.2. Es lo primero que debes probar.
