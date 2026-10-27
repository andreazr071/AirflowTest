"""Genera api/data/product_catalog.csv a partir del CSV de transacciones "Sales Transaction v.4a".

Uso (desde la raíz del repositorio):
    python api/build_catalog.py "ruta/Sales Transaction v.4a.csv"

El catálogo ya viene generado en el repositorio; este script solo se necesita para regenerarlo.
Una fila por código de producto:
  product_code      mayúsculas y sin espacios (misma regla de negocio del ETL)
  product_name      nombre normalizado (mayúsculas, espacios colapsados)
  category          categoría por palabras clave (include/datamart_etl/reference/category_rules.csv)
  category_source   regla:<PALABRA> | default  (default = ninguna regla coincidió)
  supplier_country  vacío: el CSV no trae país del proveedor (ver docs/API_PRODUCTOS.md)
  list_price        mediana del precio unitario observado
  last_sale_date    última fecha de venta
  is_active         false si no se vendió en los 90 días previos a la última fecha del archivo
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "include"))
from datamart_etl.categories import assign_categories, load_rules  # noqa: E402
from datamart_etl.transform import classify_code, normalize_code, normalize_text  # noqa: E402

INACTIVE_AFTER_DAYS = 90
OUTPUT = ROOT / "api" / "data" / "product_catalog.csv"


def build_catalog(csv_path: str) -> pd.DataFrame:
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df = pd.DataFrame({
        "product_code": normalize_code(raw["ProductNo"].str.strip()),
        "product_name": normalize_text(raw["ProductName"]),
        "price": pd.to_numeric(raw["Price"], errors="coerce"),
        "sale_date": pd.to_datetime(raw["Date"], format="%m/%d/%Y"),
    })
    df = df[(df["product_code"] != "") & (df["price"] > 0)]
    names = df.groupby(["product_code", "product_name"]).size().rename("n").reset_index()
    names = names.sort_values(["product_code", "n", "product_name"], ascending=[True, False, True])
    catalog = names.drop_duplicates("product_code")[["product_code", "product_name"]].reset_index(drop=True)

    agg = df.groupby("product_code").agg(list_price=("price", "median"), last_sale_date=("sale_date", "max"))
    catalog = catalog.join(agg, on="product_code")
    catalog["is_merchandise"] = catalog["product_code"].map(classify_code) != "NO_PRODUCTO"
    catalog = assign_categories(catalog, load_rules())
    cutoff = catalog["last_sale_date"].max() - pd.Timedelta(days=INACTIVE_AFTER_DAYS)
    catalog["is_active"] = catalog["last_sale_date"] >= cutoff
    catalog["supplier_country"] = ""
    catalog["list_price"] = catalog["list_price"].round(2)
    catalog["last_sale_date"] = catalog["last_sale_date"].dt.date.astype(str)
    return catalog[[
        "product_code", "product_name", "category", "category_source", "supplier_country",
        "list_price", "last_sale_date", "is_active",
    ]].sort_values("product_code")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result = build_catalog(sys.argv[1])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False, encoding="utf-8")
    print(f"{len(result)} productos -> {OUTPUT}")
