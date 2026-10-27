-- Repositorio analítico de DataMart S.A.S. (PostgreSQL 16)
-- Idempotente: se ejecuta al crear el contenedor (docker-entrypoint-initdb.d) y de nuevo
-- desde la primera tarea del DAG, por si el volumen de datos ya existía.
-- Diagrama y justificación: docs/MODELO_DATOS.md

CREATE SCHEMA IF NOT EXISTS dw;

-- ---------------------------------------------------------------- dimensiones
CREATE TABLE IF NOT EXISTS dw.dim_country (
    country_id   integer PRIMARY KEY,
    country_name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_id    bigint PRIMARY KEY,
    first_seen_utc timestamptz NOT NULL,
    last_seen_utc  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_code                text PRIMARY KEY,           -- MAYÚSCULAS y sin espacios
    product_name                text,                       -- nombre canónico (NULL si nunca tuvo descripción)
    code_pattern                text NOT NULL CHECK (code_pattern IN ('CATALOGO', 'ALTERNO', 'NO_PRODUCTO')),
    is_merchandise              boolean NOT NULL,           -- false: POST, M, D, bonos regalo, comisiones...
    category                    text NOT NULL,
    category_source             text NOT NULL,              -- regla:<palabra> | default | no_producto | sin_nombre
    n_description_variants_raw  integer NOT NULL,           -- textos distintos tal cual vienen
    n_description_variants_norm integer NOT NULL,           -- textos distintos tras mayúsculas/espacios
    has_inconsistent_description boolean NOT NULL           -- n_norm > 1
);

CREATE TABLE IF NOT EXISTS dw.product_description_variant (
    product_code     text NOT NULL REFERENCES dw.dim_product (product_code),
    description_norm text NOT NULL,
    occurrences      integer NOT NULL,   -- líneas (ventas + devoluciones) con este texto
    sale_occurrences integer NOT NULL,   -- solo ventas: criterio principal para elegir el canónico
    is_canonical     boolean NOT NULL,
    PRIMARY KEY (product_code, description_norm)
);

-- -------------------------------------------------------------------- hechos
-- Ventas: cantidad > 0 y precio > 0 (garantizado por CHECK).
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sale_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system     text NOT NULL CHECK (source_system IN ('data_csv', 'online_retail_ii')),
    source_row_number integer NOT NULL,
    invoice_no        text NOT NULL,
    product_code      text NOT NULL REFERENCES dw.dim_product (product_code),
    customer_id       bigint REFERENCES dw.dim_customer (customer_id),   -- NULL = cliente anónimo
    country_id        integer NOT NULL REFERENCES dw.dim_country (country_id),
    invoice_ts_utc    timestamptz NOT NULL,
    invoice_date      date GENERATED ALWAYS AS ((invoice_ts_utc AT TIME ZONE 'UTC')::date) STORED,
    quantity          integer NOT NULL CHECK (quantity > 0),
    unit_price        numeric(14, 4) NOT NULL CHECK (unit_price > 0),
    gross_revenue     numeric(18, 4) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    is_anonymous      boolean GENERATED ALWAYS AS (customer_id IS NULL) STORED
);

-- Devoluciones y ajustes: cantidad <= 0 en la fuente (se guarda en positivo).
CREATE TABLE IF NOT EXISTS dw.fact_returns (
    return_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system     text NOT NULL CHECK (source_system IN ('data_csv', 'online_retail_ii')),
    source_row_number integer NOT NULL,
    invoice_no        text NOT NULL,
    movement_type     text NOT NULL CHECK (movement_type IN ('DEVOLUCION', 'AJUSTE')),
    product_code      text NOT NULL REFERENCES dw.dim_product (product_code),
    customer_id       bigint REFERENCES dw.dim_customer (customer_id),
    country_id        integer NOT NULL REFERENCES dw.dim_country (country_id),
    invoice_ts_utc    timestamptz NOT NULL,
    invoice_date      date GENERATED ALWAYS AS ((invoice_ts_utc AT TIME ZONE 'UTC')::date) STORED,
    quantity_returned integer NOT NULL CHECK (quantity_returned >= 0),
    unit_price        numeric(14, 4) NOT NULL CHECK (unit_price >= 0),
    returned_amount   numeric(18, 4) GENERATED ALWAYS AS (quantity_returned * unit_price) STORED,
    is_anonymous      boolean GENERATED ALWAYS AS (customer_id IS NULL) STORED
);

-- Un mismo hecho no puede existir dos veces (clave compuesta usada para deduplicar fuentes).
CREATE UNIQUE INDEX IF NOT EXISTS ux_fact_sales_natural_key ON dw.fact_sales
    (invoice_no, product_code, invoice_ts_utc, quantity, unit_price, COALESCE(customer_id, -1), country_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fact_returns_natural_key ON dw.fact_returns
    (invoice_no, product_code, invoice_ts_utc, quantity_returned, unit_price, COALESCE(customer_id, -1), country_id);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date     ON dw.fact_sales (invoice_date);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product  ON dw.fact_sales (product_code);
CREATE INDEX IF NOT EXISTS ix_fact_sales_country  ON dw.fact_sales (country_id);
CREATE INDEX IF NOT EXISTS ix_fact_sales_customer ON dw.fact_sales (customer_id);
CREATE INDEX IF NOT EXISTS ix_fact_returns_date    ON dw.fact_returns (invoice_date);
CREATE INDEX IF NOT EXISTS ix_fact_returns_product ON dw.fact_returns (product_code);

-- Neto por producto y día: revenue bruto - devoluciones/ajustes del MISMO código y día (UTC).
-- Se reconstruye por completo en cada corrida (ver sql/refresh_aggregates.sql).
CREATE TABLE IF NOT EXISTS dw.agg_daily_product_net (
    invoice_date     date NOT NULL,
    product_code     text NOT NULL REFERENCES dw.dim_product (product_code),
    units_sold       bigint NOT NULL,
    units_returned   bigint NOT NULL,
    gross_revenue    numeric(18, 4) NOT NULL,
    returned_amount  numeric(18, 4) NOT NULL,
    net_revenue      numeric(18, 4) NOT NULL,
    PRIMARY KEY (invoice_date, product_code)
);

-- ------------------------------------------------------------ calidad y auditoría
CREATE TABLE IF NOT EXISTS dw.rejected_records (
    reject_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system     text NOT NULL,
    source_row_number integer NOT NULL,          -- línea del archivo de origen (1 = encabezado)
    reject_reason     text NOT NULL,
    invoice_no        text,
    stock_code        text,                      -- valores ORIGINALES, sin transformar
    description       text,
    quantity          text,
    invoice_date      text,
    unit_price        text,
    customer_id       text,
    country           text,
    loaded_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_reason ON dw.rejected_records (source_system, reject_reason);

-- Una fila por (fecha lógica, fuente, métrica): re-ejecutar el mismo día sobrescribe, no duplica.
CREATE TABLE IF NOT EXISTS dw.etl_run_audit (
    logical_date date NOT NULL,
    source_system text NOT NULL,                 -- data_csv | online_retail_ii | global
    metric        text NOT NULL,
    value         numeric NOT NULL,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (logical_date, source_system, metric)
);
