"""Pruebas de las reglas de negocio (pandas puro, sin Airflow ni base de datos)."""
import pandas as pd
import pytest

from datamart_etl import schemas as S
from datamart_etl.categories import load_rules
from datamart_etl.transform import (
    build_warehouse_tables,
    clean_source,
    normalize_code,
    unify_sources,
)

TZ = "Europe/London"
COLUMNS = ["invoice_no", "stock_code", "description", "quantity", "invoice_date", "unit_price", "customer_id", "country"]


def raw_frame(*rows):
    """Cada fila: tupla con las 8 columnas como texto, igual que sale del CSV."""
    df = pd.DataFrame(list(rows), columns=COLUMNS)
    df.insert(0, "source_row_number", range(2, len(df) + 2))
    return df


def sale(invoice="536365", code="85123A", desc="WHITE HEART", qty="6", date="12/1/2010 8:26",
         price="2.55", customer="17850", country="United Kingdom"):
    return (invoice, code, desc, qty, date, price, customer, country)


def test_codes_are_uppercase_without_spaces():
    codes = pd.Series([" 85123a ", "bank charges", "DCGS 0003"])
    assert normalize_code(codes).tolist() == ["85123A", "BANKCHARGES", "DCGS0003"]


def test_negative_quantity_is_return_not_sale():
    result = clean_source(raw_frame(sale(), sale(invoice="C536379", qty="-2")), S.SALES_DAILY, TZ)
    tables = build_warehouse_tables(result.valid, load_rules())
    assert len(tables["fact_sales"]) == 1
    assert len(tables["fact_returns"]) == 1
    row = tables["fact_returns"].iloc[0]
    assert row["movement_type"] == "DEVOLUCION" and row["quantity_returned"] == 2


def test_negative_quantity_without_c_prefix_is_adjustment():
    result = clean_source(raw_frame(sale(invoice="C1", qty="-1"), sale(invoice="537000", qty="-5", price="0")),
                          S.SALES_DAILY, TZ)
    types = build_warehouse_tables(result.valid, load_rules())["fact_returns"]["movement_type"].tolist()
    assert types == ["DEVOLUCION", "AJUSTE"] or sorted(types) == ["AJUSTE", "DEVOLUCION"]


@pytest.mark.parametrize("price", ["0", "-5.5"])
def test_sale_with_non_positive_price_is_rejected_with_reason(price):
    result = clean_source(raw_frame(sale(price=price)), S.SALES_DAILY, TZ)
    assert result.valid.empty
    assert result.rejects["reject_reason"].tolist() == [S.REJECT_SALE_NON_POSITIVE_PRICE]
    assert result.rejects["source_system"].tolist() == ["data_csv"]


def test_adjustment_with_zero_price_is_kept_but_negative_price_is_rejected():
    result = clean_source(raw_frame(sale(qty="-3", price="0"), sale(invoice="C2", qty="-3", price="-1")),
                          S.SALES_DAILY, TZ)
    assert len(result.valid) == 1
    assert result.rejects["reject_reason"].tolist() == [S.REJECT_RETURN_NEGATIVE_PRICE]


def test_invalid_values_are_rejected_not_crashing():
    result = clean_source(
        raw_frame(sale(qty="abc"), sale(price="x"), sale(date="not a date"), sale(code=""), sale(invoice="")),
        S.SALES_DAILY, TZ)
    assert sorted(result.rejects["reject_reason"]) == sorted([
        S.REJECT_BAD_QUANTITY, S.REJECT_BAD_PRICE, S.REJECT_BAD_DATE, S.REJECT_MISSING_CODE,
        S.REJECT_MISSING_INVOICE])


def test_dates_are_converted_to_utc_using_source_timezone():
    winter = clean_source(raw_frame(sale(date="12/1/2010 8:26")), S.SALES_DAILY, TZ).valid
    summer = clean_source(raw_frame(sale(date="6/1/2011 8:26")), S.SALES_DAILY, TZ).valid
    assert winter["invoice_ts_utc"].iloc[0] == pd.Timestamp("2010-12-01 08:26", tz="UTC")  # GMT = UTC
    assert summer["invoice_ts_utc"].iloc[0] == pd.Timestamp("2011-06-01 07:26", tz="UTC")  # BST = UTC+1
    # Mismo instante en otra zona también sería "igual": la columna debe estar EN UTC, no solo equivaler
    assert str(summer["invoice_ts_utc"].dtype.tz) == "UTC"


def test_history_source_accepts_iso_dates_and_its_own_column_names():
    result = clean_source(raw_frame(sale(date="2009-12-01 07:45:00")), S.HISTORY, TZ)
    assert result.valid["invoice_ts_utc"].iloc[0] == pd.Timestamp("2009-12-01 07:45", tz="UTC")


def test_missing_customer_is_kept_as_anonymous_without_inventing_an_id():
    result = clean_source(raw_frame(sale(customer="")), S.SALES_DAILY, TZ)
    assert result.valid["customer_id"].isna().all()
    assert result.rejects.empty


def test_customer_id_with_decimal_suffix_is_parsed():
    result = clean_source(raw_frame(sale(customer="13085.0")), S.HISTORY, TZ)
    assert int(result.valid["customer_id"].iloc[0]) == 13085


def test_exact_duplicates_inside_a_source_are_logged_and_first_one_kept():
    result = clean_source(raw_frame(sale(), sale()), S.SALES_DAILY, TZ)
    assert len(result.valid) == 1
    assert result.rejects["reject_reason"].tolist() == [S.REJECT_EXACT_DUPLICATE]
    assert result.rejects["source_row_number"].tolist() == [3]


def test_overlap_between_sources_keeps_the_higher_priority_source():
    daily = clean_source(raw_frame(sale()), S.SALES_DAILY, TZ).valid
    history = clean_source(raw_frame(sale(date="2010-12-01 08:26:00"), sale(invoice="500000", date="2009-12-01 08:26:00")),
                           S.HISTORY, TZ).valid
    unified, overlap = unify_sources({S.HISTORY.system: history, S.SALES_DAILY.system: daily})
    assert overlap == {"data_csv": 0, "online_retail_ii": 1}
    assert len(unified) == 2
    same_fact = unified[unified["invoice_no"] == "536365"]
    assert same_fact["source_system"].tolist() == ["data_csv"]


def test_canonical_name_is_most_frequent_sale_description_and_variants_are_counted():
    rows = [
        sale(invoice="1", desc="CANDLE HOLDER WHITE"),
        sale(invoice="2", desc="Candle Holder White"),
        sale(invoice="3", desc="candle holder white"),
        sale(invoice="4", desc="CANDLE  HOLDER   WHITE "),
        sale(invoice="5", desc="WRONG NAME"),
    ]
    valid = clean_source(raw_frame(*rows), S.SALES_DAILY, TZ).valid
    product = build_warehouse_tables(valid, load_rules())["dim_product"].iloc[0]
    assert product["product_name"] == "CANDLE HOLDER WHITE"
    assert product["n_description_variants_norm"] == 2  # mayúsculas/espacios no cuentan como variante
    assert product["n_description_variants_raw"] == 5
    assert bool(product["has_inconsistent_description"])


def test_non_merchandise_codes_are_flagged():
    valid = clean_source(raw_frame(sale(code="POST", desc="POSTAGE"), sale(invoice="2", code="DCGS0003", desc="BOXED GLASS ASHTRAY"),
                                   sale(invoice="3", code="gift_0001_20", desc="Dotcomgiftshop Gift Voucher")), S.SALES_DAILY, TZ).valid
    products = build_warehouse_tables(valid, load_rules())["dim_product"].set_index("product_code")
    assert not products.loc["POST", "is_merchandise"] and products.loc["POST", "category"] == "No producto"
    assert products.loc["DCGS0003", "is_merchandise"] and products.loc["DCGS0003", "code_pattern"] == "ALTERNO"
    assert not products.loc["GIFT_0001_20", "is_merchandise"]


def test_ids_are_deterministic_between_runs():
    rows = [sale(invoice=str(n), date=f"12/{n}/2010 9:00", country=c)
            for n, c in zip(range(1, 6), ["Germany", "France", "Spain", "Germany", "EIRE"])]
    first = build_warehouse_tables(clean_source(raw_frame(*rows), S.SALES_DAILY, TZ).valid, load_rules())
    second = build_warehouse_tables(clean_source(raw_frame(*reversed(rows)), S.SALES_DAILY, TZ).valid, load_rules())
    pd.testing.assert_frame_equal(first["dim_country"], second["dim_country"])
    assert "Ireland" in first["dim_country"]["country_name"].tolist()  # EIRE normalizado
