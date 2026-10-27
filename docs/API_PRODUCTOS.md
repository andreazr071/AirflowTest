# API interna de productos (plus 4.3)

Servicio FastAPI (`api/`) que simula el catálogo del sistema legado. Se levanta con el resto: `docker compose up`.
Documentación interactiva: <http://localhost:8000/docs> (puerto configurable con `PRODUCTS_API_PORT`).

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado y número de productos |
| `GET /products?page=1&page_size=100` | Listado paginado (`page_size` máx. 1000). Filtros opcionales: `category`, `is_active` |
| `GET /products/{codigo}` | Un producto; el código se normaliza (mayúsculas, sin espacios). 404 si no existe |

Campos: `product_code`, `product_name` (normalizado), `category`, `category_source` (`regla:<PALABRA>` o `default`),
`supplier_country`, `list_price`, `last_sale_date`, `is_active`.

## Origen de los datos y decisiones
- El catálogo (`api/data/product_catalog.csv`, 3.768 productos) se genera con `python api/build_catalog.py "<Sales Transaction v.4a.csv>"`.
  No hace falta el CSV de 43 MB para levantar el entorno.
- **`supplier_country` es siempre `null`:** el CSV no trae país del proveedor (la columna `Country` es el país del cliente). No se inventó.
- **`is_active`:** `false` si el producto no se vendió en los 90 días previos a la última fecha del archivo (630 inactivos, 3.138 activos).
- **`category`:** reglas de palabras clave del ETL; 2.779 productos caen en `Hogar` por defecto (`category_source = default`).

## Cómo lo usa el pipeline
Tarea `enriquecer_categorias_api_productos` (Variable `datamart_products_api_url`): descarga todas las páginas a Parquet.
Variable vacía = se omite y el ETL usa solo sus reglas. Variable configurada y API caída = la tarea falla y se reintenta
(3 veces), para que dos corridas con los mismos datos no produzcan categorías distintas.

Pruebas: `python -m pytest api/tests -q` (requiere `pip install fastapi httpx pytest`).
