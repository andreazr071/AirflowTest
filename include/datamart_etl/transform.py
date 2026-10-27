"""Limpieza, unificación y modelado. Funciones puras de pandas: no importan Airflow ni tocan la BD.

Flujo (cada paso es una función):
    read_source_csv -> clean_source (por fuente) -> unify_sources -> build_warehouse_tables
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import schemas as S
from .categories import Rule, assign_categories

MOVEMENT_RETURN = "DEVOLUCION"  # factura que empieza por "C" (cancelación/devolución)
MOVEMENT_ADJUSTMENT = "AJUSTE"  # cantidad <= 0 sin prefijo "C" (merma, conteo, daño)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def read_source_csv(path: str, spec: S.SourceSpec) -> pd.DataFrame:
    """Lee el CSV completo como texto y renombra a columnas canónicas.

    Todo se lee como texto (sin convertir "NA" ni vacíos a NaN) para que cada decisión de
    conversión quede explícita en clean_source y los rechazos conserven el valor original.
    """
    last_error: Exception | None = None
    raw = None
    for encoding in spec.encodings:
        try:
            raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding)
            break
        except UnicodeDecodeError as exc:  # data.csv no es UTF-8: se reintenta en latin-1
            last_error = exc
    if raw is None:
        raise last_error  # type: ignore[misc]

    rename: dict[str, str] = {}
    for column in raw.columns:
        canonical = S.canonical_header(column)
        if canonical and canonical not in rename.values():
            rename[column] = canonical
    missing = sorted(set(S.CANONICAL_COLUMNS) - set(rename.values()))
    if missing:
        raise ValueError(
            f"{path}: faltan columnas {missing}. Encabezados encontrados: {list(raw.columns)}"
        )
    df = raw[list(rename)].rename(columns=rename)
    df.insert(0, "source_row_number", np.arange(2, len(df) + 2))  # línea del archivo (1 = encabezado)
    return df


# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------
def normalize_code(codes: pd.Series) -> pd.Series:
    """Regla de negocio: códigos en mayúsculas y sin espacios."""
    return codes.str.replace(r"\s+", "", regex=True).str.upper()


def normalize_text(texts: pd.Series) -> pd.Series:
    """Mayúsculas, sin espacios repetidos ni en los bordes (para comparar descripciones)."""
    return texts.str.replace(r"\s+", " ", regex=True).str.strip().str.upper()


def normalize_country(countries: pd.Series) -> pd.Series:
    mapped = countries.str.upper().map(S.COUNTRY_ALIASES)
    result = mapped.fillna(countries)
    return result.where(result != "", "Unspecified")


def parse_timestamps(values: pd.Series, formats: tuple[str, ...]) -> pd.Series:
    """Prueba cada formato en orden; lo que no coincide con ninguno queda NaT (se rechaza)."""
    result: pd.Series | None = None
    for fmt in formats:
        parsed = pd.to_datetime(values, format=fmt, errors="coerce")
        result = parsed if result is None else result.fillna(parsed)
        if result.notna().all():
            break
    return result  # type: ignore[return-value]


def local_to_utc(local_naive: pd.Series, source_timezone: str) -> pd.Series:
    """Hora local de la tienda -> UTC.

    Hora ambigua (cambio de horario de otoño): se asume horario de verano (primera ocurrencia).
    Hora inexistente (cambio de primavera): se corre hacia adelante.
    """
    ambiguous = np.ones(len(local_naive), dtype=bool)
    localized = local_naive.dt.tz_localize(
        source_timezone, ambiguous=ambiguous, nonexistent="shift_forward"
    )
    return localized.dt.tz_convert("UTC")


# ---------------------------------------------------------------------------
# Limpieza por fuente
# ---------------------------------------------------------------------------
@dataclass
class CleanResult:
    valid: pd.DataFrame
    rejects: pd.DataFrame
    stats: dict = field(default_factory=dict)


REJECT_COLUMNS = [
    "source_system", "source_row_number", "reject_reason", "invoice_no", "stock_code",
    "description", "quantity", "invoice_date", "unit_price", "customer_id", "country",
]  # fmt: skip


def clean_source(raw: pd.DataFrame, spec: S.SourceSpec, source_timezone: str) -> CleanResult:
    """Valida y estandariza una fuente. Cada fila queda en `valid` o en `rejects` con un motivo."""
    df = raw.copy()
    for column in S.CANONICAL_COLUMNS:
        df[column] = df[column].fillna("").astype(str).str.strip()
    df["invoice_no"] = df["invoice_no"].str.upper()
    df["product_code"] = normalize_code(df["stock_code"])

    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    price = pd.to_numeric(df["unit_price"], errors="coerce")
    customer = pd.to_numeric(df["customer_id"], errors="coerce")
    invoice_utc = local_to_utc(parse_timestamps(df["invoice_date"], spec.date_formats), source_timezone)

    quantity_is_integer = quantity.notna() & (quantity == quantity.round())
    customer_is_bad = (df["customer_id"] != "") & (customer.isna() | (customer != customer.round()))

    # Reglas en orden de prioridad: si varias aplican, el motivo es el primero.
    rules = [
        (df["invoice_no"].eq(""), S.REJECT_MISSING_INVOICE),
        (df["product_code"].eq(""), S.REJECT_MISSING_CODE),
        (invoice_utc.isna(), S.REJECT_BAD_DATE),
        (~quantity_is_integer, S.REJECT_BAD_QUANTITY),
        (price.isna(), S.REJECT_BAD_PRICE),
        (customer_is_bad, S.REJECT_BAD_CUSTOMER),
        # Regla de negocio: una venta válida no puede tener precio <= 0.
        ((quantity > 0) & (price <= 0), S.REJECT_SALE_NON_POSITIVE_PRICE),
        # Una devolución/ajuste puede valer 0 (merma sin valor) pero nunca ser negativa.
        ((quantity <= 0) & (price < 0), S.REJECT_RETURN_NEGATIVE_PRICE),
    ]
    df["reject_reason"] = np.select(
        [condition.to_numpy(dtype=bool) for condition, _ in rules],
        [reason for _, reason in rules],
        default="",
    )

    valid = pd.DataFrame(
        {
            "source_system": spec.system,
            "source_row_number": df["source_row_number"],
            "invoice_no": df["invoice_no"],
            "product_code": df["product_code"],
            "description_raw": df["description"],
            "description_norm": normalize_text(df["description"]),
            "quantity": quantity,
            "unit_price": price,
            "invoice_ts_utc": invoice_utc,
            "customer_id": customer,  # vacío -> NaN: cliente anónimo (se conserva, sin id inventado)
            "country": normalize_country(df["country"]),
        }
    )
    valid = valid.loc[df["reject_reason"] == ""].copy()
    valid["quantity"] = valid["quantity"].astype("int64")
    valid["customer_id"] = valid["customer_id"].astype("Int64")

    # Duplicados exactos dentro de la misma fuente: se conserva la primera aparición.
    is_duplicate = valid.duplicated(subset=S.DEDUP_KEY, keep="first")
    df.loc[valid.index[is_duplicate], "reject_reason"] = S.REJECT_EXACT_DUPLICATE
    valid = valid.loc[~is_duplicate]

    rejected_index = df.index[df["reject_reason"] != ""]
    rejects = raw.loc[rejected_index, ["source_row_number", *S.CANONICAL_COLUMNS]].copy()
    rejects.insert(0, "source_system", spec.system)
    rejects.insert(2, "reject_reason", df.loc[rejected_index, "reject_reason"].to_numpy())
    rejects = rejects[REJECT_COLUMNS]

    stats = {
        "rows_read": int(len(raw)),
        "rows_rejected": int(len(rejects)),
        "rows_valid": int(len(valid)),
        "rejected_by_reason": {
            str(k): int(v) for k, v in rejects["reject_reason"].value_counts().items()
        },
        "anonymous_rows_valid": int(valid["customer_id"].isna().sum()),
    }
    return CleanResult(valid=valid, rejects=rejects, stats=stats)


# ---------------------------------------------------------------------------
# Unificación de fuentes
# ---------------------------------------------------------------------------
def unify_sources(
    valid_by_source: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Une las fuentes y elimina duplicados entre ellas.

    Un hecho es duplicado si coincide en TODA la clave S.DEDUP_KEY. Gana la fuente de menor
    `priority` (data.csv, el volcado operativo); la copia de la otra fuente se descarta.
    """
    ordered = sorted(valid_by_source, key=lambda system: S.SOURCES[system].priority)
    combined = pd.concat([valid_by_source[s] for s in ordered], ignore_index=True)
    is_overlap = combined.duplicated(subset=S.DEDUP_KEY, keep="first")
    overlap_by_source = {s: 0 for s in ordered}
    overlap_by_source.update(
        {str(k): int(v) for k, v in combined.loc[is_overlap, "source_system"].value_counts().items()}
    )
    unified = combined.loc[~is_overlap].sort_values(
        ["invoice_ts_utc", "invoice_no", "product_code", "source_system", "source_row_number"],
        kind="mergesort",  # orden estable y determinista -> ids idénticos en cada corrida
    )
    return unified.reset_index(drop=True), overlap_by_source


# ---------------------------------------------------------------------------
# Modelo analítico
# ---------------------------------------------------------------------------
def classify_code(product_code: str) -> str:
    if S.NON_MERCHANDISE_CODE.fullmatch(product_code):
        return "NO_PRODUCTO"
    if S.CATALOG_CODE.fullmatch(product_code):
        return "CATALOGO"
    return "ALTERNO"  # empieza con letras pero es mercancía (p. ej. DCGS0003)


def build_product_tables(
    unified: pd.DataFrame, rules: list[Rule], api_categories: dict[str, str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (dim_product, product_description_variant).

    Nombre canónico = la descripción normalizada (mayúsculas, espacios colapsados) más frecuente
    entre las VENTAS del código; desempata por apariciones totales y luego alfabéticamente.
    """
    with_description = unified.loc[unified["description_norm"] != ""]
    all_counts = (
        with_description.groupby(["product_code", "description_norm"]).size().rename("occurrences")
    )
    sale_counts = (
        with_description.loc[with_description["quantity"] > 0]
        .groupby(["product_code", "description_norm"])
        .size()
        .rename("sale_occurrences")
    )
    variants = pd.concat([all_counts, sale_counts], axis=1).fillna(0).astype("int64").reset_index()
    variants = variants.sort_values(
        ["product_code", "sale_occurrences", "occurrences", "description_norm"],
        ascending=[True, False, False, True],
        kind="mergesort",
    )
    variants["is_canonical"] = ~variants.duplicated("product_code", keep="first")

    canonical = variants.loc[variants["is_canonical"]].set_index("product_code")["description_norm"]
    n_norm = variants.groupby("product_code").size()
    n_raw = with_description.groupby("product_code")["description_raw"].nunique()

    products = pd.DataFrame({"product_code": np.sort(unified["product_code"].unique())})
    products["product_name"] = products["product_code"].map(canonical)
    products["code_pattern"] = products["product_code"].map(classify_code)
    products["is_merchandise"] = products["code_pattern"] != "NO_PRODUCTO"
    products["n_description_variants_raw"] = products["product_code"].map(n_raw).fillna(0).astype("int64")
    products["n_description_variants_norm"] = products["product_code"].map(n_norm).fillna(0).astype("int64")
    products["has_inconsistent_description"] = products["n_description_variants_norm"] > 1
    products = assign_categories(products, rules, api_categories)

    variants = variants[["product_code", "description_norm", "occurrences", "sale_occurrences", "is_canonical"]]
    return products, variants.reset_index(drop=True)


def build_warehouse_tables(
    unified: pd.DataFrame, rules: list[Rule], api_categories: dict[str, str] | None = None
) -> dict[str, pd.DataFrame]:
    """Convierte el DataFrame unificado en las tablas del modelo (ver docs/MODELO_DATOS.md)."""
    countries = pd.DataFrame({"country_name": np.sort(unified["country"].unique())})
    countries.insert(0, "country_id", np.arange(1, len(countries) + 1))
    country_id = countries.set_index("country_name")["country_id"]

    customers = (
        unified.dropna(subset=["customer_id"])
        .groupby("customer_id")["invoice_ts_utc"]
        .agg(first_seen_utc="min", last_seen_utc="max")
        .reset_index()
        .sort_values("customer_id")
    )

    products, variants = build_product_tables(unified, rules, api_categories)

    facts = unified.assign(country_id=unified["country"].map(country_id).astype("int64"))
    is_sale = facts["quantity"] > 0
    fact_columns = [
        "source_system", "source_row_number", "invoice_no", "product_code", "customer_id",
        "country_id", "invoice_ts_utc", "quantity", "unit_price",
    ]  # fmt: skip

    fact_sales = facts.loc[is_sale, fact_columns].reset_index(drop=True)

    movements = facts.loc[~is_sale, fact_columns].copy()
    movements["movement_type"] = np.where(
        movements["invoice_no"].str.startswith("C"), MOVEMENT_RETURN, MOVEMENT_ADJUSTMENT
    )
    movements["quantity_returned"] = -movements["quantity"]  # se guarda en positivo
    fact_returns = movements.drop(columns="quantity").reset_index(drop=True)

    return {
        "dim_country": countries,
        "dim_customer": customers,
        "dim_product": products,
        "product_description_variant": variants,
        "fact_sales": fact_sales,
        "fact_returns": fact_returns,
    }


def build_audit_metrics(
    stats_by_source: dict[str, dict],
    overlap_by_source: dict[str, int],
    tables: dict[str, pd.DataFrame],
) -> dict[str, dict[str, float]]:
    """Métricas por fuente (+ 'global') que se guardan en etl_run_audit y sirven para conciliar."""
    metrics: dict[str, dict[str, float]] = {}
    for system, stats in stats_by_source.items():
        entry: dict[str, float] = {
            "rows_read": stats["rows_read"],
            "rows_rejected": stats["rows_rejected"],
            "rows_valid_after_source_dedup": stats["rows_valid"],
            "rows_dropped_overlap_with_higher_priority_source": overlap_by_source.get(system, 0),
            "rows_loaded_sales": int((tables["fact_sales"]["source_system"] == system).sum()),
            "rows_loaded_returns": int((tables["fact_returns"]["source_system"] == system).sum()),
        }
        for reason, count in stats["rejected_by_reason"].items():
            entry[f"rejected__{reason}"] = count
        metrics[system] = entry

    sales, returns = tables["fact_sales"], tables["fact_returns"]
    metrics["global"] = {
        "gross_revenue": round(float((sales["quantity"] * sales["unit_price"]).sum()), 2),
        "returned_amount": round(float((returns["quantity_returned"] * returns["unit_price"]).sum()), 2),
        "rows_fact_sales": len(sales),
        "rows_fact_returns": len(returns),
        "distinct_product_codes": len(tables["dim_product"]),
        "anonymous_sale_rows": int(sales["customer_id"].isna().sum()),
    }
    return metrics
