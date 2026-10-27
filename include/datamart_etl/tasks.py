"""Callables de las tareas del DAG. Aquí solo hay pegamento con Airflow (Variables, Connections,
archivos intermedios); la lógica de negocio está en transform.py, quality.py y warehouse.py.

Entre tareas no se pasan DataFrames por XCom (son millones de filas): se intercambian archivos
Parquet en el directorio de trabajo compartido (Variable `datamart_work_dir`).
"""
from __future__ import annotations

import json
import logging
import requests
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from airflow.exceptions import AirflowFailException
from airflow.models import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook

from . import schemas as S
from .categories import load_rules
from .quality import check_tables
from .transform import (
    build_audit_metrics,
    build_warehouse_tables,
    clean_source,
    read_source_csv,
    unify_sources,
)
from .warehouse import apply_ddl, fetch_load_summary, load_warehouse

log = logging.getLogger(__name__)

WAREHOUSE_CONN_ID = "datamart_warehouse"  # Airflow Connection creada por scripts/init_airflow.sh
OUTPUT_TABLES = [
    "dim_country", "dim_customer", "dim_product", "product_description_variant",
    "fact_sales", "fact_returns", "rejected_records",
]  # fmt: skip
REQUIRED_VARIABLES = [
    "datamart_raw_data_dir", "datamart_work_dir", "datamart_sales_file",
    "datamart_history_file", "datamart_source_timezone", "datamart_max_reject_ratio",
]  # fmt: skip


@dataclass(frozen=True)
class Settings:
    raw_data_dir: Path
    work_dir: Path
    sales_file: str
    history_file: str
    source_timezone: str
    max_reject_ratio: float


def load_settings() -> Settings:
    """Lee las Airflow Variables operativas; falla con un mensaje claro si falta alguna."""
    missing = [name for name in REQUIRED_VARIABLES if Variable.get(name, default_var=None) is None]
    if missing:
        raise AirflowFailException(
            f"Faltan Airflow Variables {missing}. Las crea scripts/init_airflow.sh al levantar el "
            "entorno; revisa los logs del servicio airflow-init."
        )
    return Settings(
        raw_data_dir=Path(Variable.get("datamart_raw_data_dir")),
        work_dir=Path(Variable.get("datamart_work_dir")),
        sales_file=Variable.get("datamart_sales_file"),
        history_file=Variable.get("datamart_history_file"),
        source_timezone=Variable.get("datamart_source_timezone"),
        max_reject_ratio=float(Variable.get("datamart_max_reject_ratio")),
    )


API_PRODUCTS_FILE = "api_products.parquet"
API_PAGE_SIZE = 1000


def _read_api_categories(work_dir: Path) -> dict[str, str] | None:
    """Categorías traídas de la API (código -> categoría); None si la API no está configurada.

    Se ignoran las categorías que la API asignó "por defecto": son una suposición, no una clasificación.
    """
    staged = work_dir / API_PRODUCTS_FILE
    if not staged.exists():
        return None
    products = pd.read_parquet(staged)
    classified = products.loc[products["category_source"] != "default"]
    return dict(zip(classified["product_code"], classified["category"]))


def _warehouse_connection():
    return PostgresHook(postgres_conn_id=WAREHOUSE_CONN_ID).get_conn()


def _read_outputs(work_dir: Path) -> tuple[dict[str, pd.DataFrame], dict]:
    tables = {name: pd.read_parquet(work_dir / f"out_{name}.parquet") for name in OUTPUT_TABLES}
    audit = json.loads((work_dir / "audit.json").read_text(encoding="utf-8"))
    return tables, audit


# --------------------------------------------------------------------------- tareas
def crear_esquema_warehouse() -> None:
    """Verifica Variables y conexión, y crea el esquema si no existe (DDL idempotente)."""
    settings = load_settings()
    log.info("Variables OK. raw=%s work=%s tz=%s", settings.raw_data_dir, settings.work_dir, settings.source_timezone)
    conn = _warehouse_connection()
    try:
        apply_ddl(conn)
    finally:
        conn.close()
    log.info("Esquema dw verificado en el warehouse.")


def extraer_fuente(system: str) -> None:
    """Lee un CSV crudo (como texto) y lo deja como Parquet en el directorio de trabajo."""
    settings = load_settings()
    spec = S.SOURCES[system]
    file_name = settings.sales_file if system == S.SALES_DAILY.system else settings.history_file
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    staged = settings.work_dir / f"raw_{system}.parquet"
    staged.unlink(missing_ok=True)  # nunca reutilizar la extracción de una corrida anterior
    path = settings.raw_data_dir / file_name if file_name else None
    if path is None or not path.is_file():
        if spec.required:
            raise AirflowFailException(
                f"No existe {path}. Copia {file_name} a la carpeta RAW_DATA_DIR del host (ver README)."
            )
        log.warning("Fuente opcional %s omitida: no hay archivo (%s). El pipeline sigue sin ella.", system, file_name)
        return
    raw = read_source_csv(str(path), spec)
    raw.to_parquet(staged, index=False)
    empty = {c: int((raw[c].str.strip() == "").sum()) for c in S.CANONICAL_COLUMNS}
    log.info("%s: %d filas leídas de %s. Vacíos por columna: %s", spec.description, len(raw), path, empty)


def enriquecer_categorias_api() -> None:
    """Descarga el catálogo de la API interna de productos (todas las páginas) a un Parquet.

    Variable `datamart_products_api_url` vacía o ausente = API no configurada: se omite y la
    transformación usa solo las reglas de categoría. Si está configurada y falla, la tarea falla
    y se reintenta (así dos corridas con los mismos datos no producen categorías distintas).
    """
    work_dir = Path(Variable.get("datamart_work_dir", default_var="/opt/airflow/data/work"))
    base_url = (Variable.get("datamart_products_api_url", default_var="") or "").rstrip("/")
    work_dir.mkdir(parents=True, exist_ok=True)
    staged = work_dir / API_PRODUCTS_FILE
    staged.unlink(missing_ok=True)  # nunca reutilizar la descarga de una corrida anterior
    if not base_url:
        log.warning("API de productos no configurada (datamart_products_api_url vacía): se usan solo las reglas.")
        return

    items: list[dict] = []
    page = 1
    while True:
        response = requests.get(
            f"{base_url}/products", params={"page": page, "page_size": API_PAGE_SIZE}, timeout=30
        )
        response.raise_for_status()
        body = response.json()
        items.extend(body["items"])
        if page >= body["total_pages"]:
            break
        page += 1
    if not items:
        raise AirflowFailException(f"La API {base_url} devolvió un catálogo vacío.")
    pd.DataFrame(items).to_parquet(staged, index=False)
    log.info("API de productos: %d productos descargados de %s", len(items), base_url)


def transformar_y_unificar() -> None:
    """Limpia cada fuente, une, deduplica, modela y escribe las tablas finales + auditoría."""
    settings = load_settings()
    work = settings.work_dir
    for stale in work.glob("out_*.parquet"):
        stale.unlink()  # nunca mezclar salidas de corridas anteriores

    valid_by_source: dict[str, pd.DataFrame] = {}
    rejects: list[pd.DataFrame] = []
    stats: dict[str, dict] = {}
    for system, spec in S.SOURCES.items():
        staged = work / f"raw_{system}.parquet"
        if not staged.exists():  # fuente opcional omitida en la extracción
            continue
        raw = pd.read_parquet(staged)
        result = clean_source(raw, spec, settings.source_timezone)
        del raw  # liberar memoria antes de procesar la siguiente fuente
        valid_by_source[system], stats[system] = result.valid, result.stats
        rejects.append(result.rejects)
        log.info("%s: %s", system, result.stats)

    unified, overlap = unify_sources(valid_by_source)
    log.info("Filas descartadas por solapamiento entre fuentes: %s", overlap)

    api_categories = _read_api_categories(work)
    log.info("Categorías de la API disponibles: %s", "no" if api_categories is None else len(api_categories))
    tables = build_warehouse_tables(unified, load_rules(), api_categories)
    tables["rejected_records"] = pd.concat(rejects, ignore_index=True)
    audit = build_audit_metrics(stats, overlap, tables)

    for name, frame in tables.items():
        frame.to_parquet(work / f"out_{name}.parquet", index=False)
    (work / "audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Tablas generadas: %s", {name: len(frame) for name, frame in tables.items()})


def validar_calidad_pre_carga() -> None:
    """Puerta de calidad: si algo no cumple las reglas, falla SIN reintentar y no se carga nada."""
    settings = load_settings()
    tables, audit = _read_outputs(settings.work_dir)
    failures = check_tables(tables, audit, settings.max_reject_ratio)
    if failures:
        raise AirflowFailException("Validación de calidad fallida:\n- " + "\n- ".join(failures))
    log.info("Validación de calidad OK. Auditoría global: %s", audit["global"])


def cargar_warehouse(logical_date: str) -> None:
    """Carga transaccional (TRUNCATE + COPY + agregados). Re-ejecutar produce el mismo resultado."""
    settings = load_settings()
    tables, audit = _read_outputs(settings.work_dir)
    conn = _warehouse_connection()
    try:
        load_warehouse(conn, tables, audit, date.fromisoformat(logical_date))
    finally:
        conn.close()
    log.info("Carga completada para la fecha lógica %s", logical_date)


def validar_carga_warehouse() -> None:
    """Concilia lo que quedó en PostgreSQL contra lo que produjo la transformación."""
    settings = load_settings()
    _, audit = _read_outputs(settings.work_dir)
    expected = audit["global"]
    conn = _warehouse_connection()
    try:
        actual = fetch_load_summary(conn)
    finally:
        conn.close()

    rejected_expected = sum(m["rows_rejected"] for system, m in audit.items() if system != "global")
    problems = []
    for key, exp in (
        ("fact_sales", expected["rows_fact_sales"]),
        ("fact_returns", expected["rows_fact_returns"]),
        ("dim_product", expected["distinct_product_codes"]),
        ("rejected_records", rejected_expected),
    ):
        if actual[key] != exp:
            problems.append(f"{key}: warehouse={actual[key]:.0f} esperado={exp:.0f}")
    for key, exp in (("gross_revenue", expected["gross_revenue"]), ("returned_amount", expected["returned_amount"])):
        if abs(actual[key] - exp) > 0.05:  # la auditoría redondea a 2 decimales
            problems.append(f"{key}: warehouse={actual[key]:.2f} esperado={exp:.2f}")
    if abs(actual["net_revenue"] - (actual["gross_revenue"] - actual["returned_amount"])) > 0.05:
        problems.append("net_revenue != gross_revenue - returned_amount")
    if problems:
        raise AirflowFailException("Conciliación post-carga fallida:\n- " + "\n- ".join(problems))
    log.info("Conciliación post-carga OK: %s", actual)
