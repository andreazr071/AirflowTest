# Seeds (datos de prueba)

Muestras pequeñas y REALES de los dos datasets, para correr el pipeline desde cero sin descargar nada:

- `data.csv`: ~1.200 filas de `carrie1/ecommerce-data` (primeras facturas + casos límite: precio 0,
  cantidades negativas, sin customer ID, códigos en minúscula, POST, duplicados, otros países). Codificación latin-1, como el original.
- `online_retail_II.csv`: ~2.600 filas de Online Retail II (UCI, mismo tipo de negocio): las primeras
  facturas de 2009 (no solapan) + las filas cuyas facturas también están en `data.csv` (solapan, para probar la deduplicación).

Uso: `RAW_DATA_DIR=./data/seeds` en tu `.env`. Los archivos completos van en `data/raw/` (no se versionan).
