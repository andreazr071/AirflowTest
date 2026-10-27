"""Integración contra PostgreSQL real. Se omite si no hay WAREHOUSE_TEST_DSN.
Ej.: WAREHOUSE_TEST_DSN="host=127.0.0.1 dbname=datamart_dw user=dw_user password=..." pytest tests
ATENCIÓN: vacía las tablas del esquema dw de esa base; no la apuntes a datos que quieras conservar."""
import os
from datetime import date

import pytest

psycopg2 = pytest.importorskip("psycopg2")
pytest.importorskip("pandas")
from datamart_etl import schemas as S  # noqa: E402
from datamart_etl.categories import load_rules  # noqa: E402
from datamart_etl.transform import build_audit_metrics, build_warehouse_tables, clean_source, unify_sources  # noqa: E402
from datamart_etl.warehouse import apply_ddl, fetch_load_summary, load_warehouse  # noqa: E402
from test_transform import raw_frame, sale  # noqa: E402

DSN = os.environ.get("WAREHOUSE_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="define WAREHOUSE_TEST_DSN para correr")


def build():
    result = clean_source(raw_frame(sale(), sale(invoice="C536379", qty="-2"), sale(invoice="2", price="0")),
                          S.SALES_DAILY, "Europe/London")
    unified, overlap = unify_sources({"data_csv": result.valid})
    tables = build_warehouse_tables(unified, load_rules())
    tables["rejected_records"] = result.rejects
    return tables, build_audit_metrics({"data_csv": result.stats}, overlap, tables)


@pytest.fixture
def conn():
    connection = psycopg2.connect(DSN)
    apply_ddl(connection)
    yield connection
    connection.close()


def test_loading_twice_gives_same_result_and_net_identity(conn):
    tables, audit = build()
    load_warehouse(conn, tables, audit, date(2026, 10, 26))
    first = fetch_load_summary(conn)
    load_warehouse(conn, tables, audit, date(2026, 10, 26))
    assert fetch_load_summary(conn) == first
    assert first["fact_sales"] == 1 and first["fact_returns"] == 1 and first["rejected_records"] == 1
    assert first["net_revenue"] == pytest.approx(first["gross_revenue"] - first["returned_amount"])


def test_failed_load_rolls_back_and_keeps_previous_data(conn):
    tables, audit = build()
    load_warehouse(conn, tables, audit, date(2026, 10, 26))
    before = fetch_load_summary(conn)
    broken = dict(tables)
    broken["fact_returns"] = tables["fact_returns"].assign(movement_type="INVALIDO")  # viola el CHECK
    with pytest.raises(psycopg2.Error):
        load_warehouse(conn, broken, audit, date(2026, 10, 26))
    assert fetch_load_summary(conn) == before
