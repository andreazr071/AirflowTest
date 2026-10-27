"""Carga al repositorio analítico (PostgreSQL). Recibe una conexión psycopg2; no depende de Airflow.

Idempotencia: cada corrida hace TRUNCATE + COPY + recálculo de agregados dentro de UNA
transacción. Si algo falla, PostgreSQL revierte todo y el warehouse queda como estaba; si se
ejecuta dos veces con los mismos archivos, el resultado es idéntico (ids incluidos, porque los
DataFrames se cargan en orden determinista y las identidades se reinician).
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"  # /opt/airflow/sql en el contenedor
DDL_PATH = SQL_DIR / "ddl" / "001_schema.sql"
REFRESH_PATH = SQL_DIR / "refresh_aggregates.sql"

TRUNCATE_ALL = """
TRUNCATE dw.agg_daily_product_net, dw.fact_sales, dw.fact_returns,
         dw.product_description_variant, dw.dim_product, dw.dim_customer, dw.dim_country,
         dw.rejected_records
RESTART IDENTITY
"""

# tabla destino -> columnas, en el orden en que se carga (dimensiones antes que hechos)
LOAD_PLAN: list[tuple[str, str, list[str]]] = [
    ("dim_country", "dw.dim_country", ["country_id", "country_name"]),
    ("dim_customer", "dw.dim_customer", ["customer_id", "first_seen_utc", "last_seen_utc"]),
    ("dim_product", "dw.dim_product", [
        "product_code", "product_name", "code_pattern", "is_merchandise", "category",
        "category_source", "n_description_variants_raw", "n_description_variants_norm",
        "has_inconsistent_description",
    ]),
    ("product_description_variant", "dw.product_description_variant", [
        "product_code", "description_norm", "occurrences", "sale_occurrences", "is_canonical",
    ]),
    ("fact_sales", "dw.fact_sales", [
        "source_system", "source_row_number", "invoice_no", "product_code", "customer_id",
        "country_id", "invoice_ts_utc", "quantity", "unit_price",
    ]),
    ("fact_returns", "dw.fact_returns", [
        "source_system", "source_row_number", "invoice_no", "movement_type", "product_code",
        "customer_id", "country_id", "invoice_ts_utc", "quantity_returned", "unit_price",
    ]),
    ("rejected_records", "dw.rejected_records", [
        "source_system", "source_row_number", "reject_reason", "invoice_no", "stock_code",
        "description", "quantity", "invoice_date", "unit_price", "customer_id", "country",
    ]),
]  # fmt: skip


def apply_ddl(conn) -> None:
    """Crea esquema y tablas si no existen (seguro de repetir)."""
    with conn, conn.cursor() as cursor:
        cursor.execute(DDL_PATH.read_text(encoding="utf-8"))


def _copy(cursor, table: str, frame: pd.DataFrame, columns: list[str], chunk_rows: int = 200_000) -> None:
    sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '')"
    for start in range(0, len(frame), chunk_rows):
        buffer = io.StringIO()
        frame.iloc[start : start + chunk_rows][columns].to_csv(buffer, index=False, header=False)
        buffer.seek(0)
        cursor.copy_expert(sql, buffer)


def load_warehouse(
    conn,
    tables: dict[str, pd.DataFrame],
    audit: dict[str, dict[str, float]],
    logical_date: date,
) -> None:
    """Reemplaza el contenido del warehouse por `tables` en una sola transacción."""
    with conn:  # commit al salir bien, rollback si hay excepción
        with conn.cursor() as cursor:
            cursor.execute(TRUNCATE_ALL)
            for key, table, columns in LOAD_PLAN:
                _copy(cursor, table, tables[key], columns)
            cursor.execute(REFRESH_PATH.read_text(encoding="utf-8"))

            rows = [
                (logical_date, system, metric, float(value))
                for system, metrics in audit.items()
                for metric, value in metrics.items()
            ]
            execute_values(
                cursor,
                """INSERT INTO dw.etl_run_audit (logical_date, source_system, metric, value)
                   VALUES %s
                   ON CONFLICT (logical_date, source_system, metric)
                   DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                rows,
            )


def fetch_load_summary(conn) -> dict[str, float]:
    """Totales leídos del warehouse, para conciliarlos contra lo que dijo la transformación."""
    sql = """
        SELECT
          (SELECT count(*) FROM dw.fact_sales),
          (SELECT count(*) FROM dw.fact_returns),
          (SELECT COALESCE(SUM(gross_revenue), 0) FROM dw.fact_sales),
          (SELECT COALESCE(SUM(returned_amount), 0) FROM dw.fact_returns),
          (SELECT COALESCE(SUM(net_revenue), 0) FROM dw.agg_daily_product_net),
          (SELECT count(*) FROM dw.dim_product),
          (SELECT count(*) FROM dw.rejected_records)
    """
    with conn.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()
    conn.rollback()  # solo lectura: cierra la transacción implícita
    names = ["fact_sales", "fact_returns", "gross_revenue", "returned_amount",
             "net_revenue", "dim_product", "rejected_records"]  # fmt: skip
    return {name: float(value) for name, value in zip(names, row)}
