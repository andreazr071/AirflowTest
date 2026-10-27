"""Validaciones de calidad previas a la carga. Devuelve una lista de fallos (vacía = todo bien)."""
from __future__ import annotations

import pandas as pd

PLAUSIBLE_START = pd.Timestamp("2000-01-01", tz="UTC")


def _bad_codes(codes: pd.Series) -> int:
    normalized = codes.str.replace(r"\s+", "", regex=True).str.upper()
    return int((codes != normalized).sum())


def check_tables(
    tables: dict[str, pd.DataFrame],
    audit: dict[str, dict[str, float]],
    max_reject_ratio: float,
) -> list[str]:
    failures: list[str] = []
    sales, returns = tables["fact_sales"], tables["fact_returns"]
    products = tables["dim_product"]

    # --- reglas de negocio
    if (sales["quantity"] <= 0).any():
        failures.append("fact_sales contiene cantidades <= 0 (deben ir a fact_returns)")
    if (sales["unit_price"] <= 0).any():
        failures.append("fact_sales contiene precios unitarios <= 0 (deben rechazarse)")
    if (returns["quantity_returned"] < 0).any() or (returns["unit_price"] < 0).any():
        failures.append("fact_returns contiene cantidades o precios negativos")

    for name, codes in (
        ("fact_sales", sales["product_code"]),
        ("fact_returns", returns["product_code"]),
        ("dim_product", products["product_code"]),
    ):
        if (count := _bad_codes(codes)):
            failures.append(f"{name}: {count} códigos sin normalizar (mayúsculas/sin espacios)")

    # --- fechas en UTC y plausibles
    upper_bound = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)
    for name, frame in (("fact_sales", sales), ("fact_returns", returns)):
        series = frame["invoice_ts_utc"]
        if not (isinstance(series.dtype, pd.DatetimeTZDtype) and str(series.dtype.tz) == "UTC"):
            failures.append(f"{name}.invoice_ts_utc no está en UTC (dtype={series.dtype})")
        elif len(series) and (series.min() < PLAUSIBLE_START or series.max() > upper_bound):
            failures.append(f"{name}.invoice_ts_utc fuera de rango plausible ({series.min()} .. {series.max()})")

    # --- duplicados e integridad referencial
    natural_key = ["invoice_no", "product_code", "invoice_ts_utc", "unit_price", "customer_id", "country_id"]
    for name, frame, quantity_column in (
        ("fact_sales", sales, "quantity"),
        ("fact_returns", returns, "quantity_returned"),
    ):
        if (count := int(frame.duplicated(subset=[*natural_key, quantity_column]).sum())):
            failures.append(f"{name}: {count} filas duplicadas por clave natural")
    for column, dimension, dim_key in (
        ("product_code", products, "product_code"),
        ("country_id", tables["dim_country"], "country_id"),
    ):
        for name, frame in (("fact_sales", sales), ("fact_returns", returns)):
            orphans = ~frame[column].isin(dimension[dim_key])
            if orphans.any():
                failures.append(f"{name}.{column}: {int(orphans.sum())} valores sin dimensión")
    known_customers = tables["dim_customer"]["customer_id"]
    for name, frame in (("fact_sales", sales), ("fact_returns", returns)):
        ids = frame["customer_id"].dropna()
        if (~ids.isin(known_customers)).any():
            failures.append(f"{name}.customer_id: clientes sin dimensión")

    variants = tables["product_description_variant"]
    if variants.groupby("product_code")["is_canonical"].sum().ne(1).any():
        failures.append("product_description_variant: hay productos sin exactamente un nombre canónico")

    # --- conciliación de filas por fuente
    for system, m in ((s, v) for s, v in audit.items() if s != "global"):
        if m["rows_read"] != m["rows_rejected"] + m["rows_valid_after_source_dedup"]:
            failures.append(f"{system}: leídas != rechazadas + válidas")
        loaded = m["rows_loaded_sales"] + m["rows_loaded_returns"]
        if m["rows_valid_after_source_dedup"] != loaded + m["rows_dropped_overlap_with_higher_priority_source"]:
            failures.append(f"{system}: válidas != cargadas + descartadas por solapamiento")
        ratio = m["rows_rejected"] / m["rows_read"] if m["rows_read"] else 0.0
        if ratio > max_reject_ratio:
            failures.append(
                f"{system}: tasa de rechazo {ratio:.2%} supera el máximo permitido {max_reject_ratio:.2%}"
            )
    return failures
