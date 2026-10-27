"""API interna de productos de DataMart (sección 4.3 del enunciado).

Simula el sistema legado de catálogo. Solo lectura; el catálogo se carga una vez al iniciar
desde un CSV (CATALOG_PATH). Documentación interactiva en /docs.
"""
from __future__ import annotations

import csv
import math
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", Path(__file__).resolve().parents[1] / "data" / "product_catalog.csv"))
MAX_PAGE_SIZE = 1000


class Product(BaseModel):
    product_code: str
    product_name: str
    category: str
    category_source: str  # regla:<PALABRA> | default (ninguna regla coincidió)
    supplier_country: str | None  # el origen de datos no lo trae: siempre null
    list_price: float
    last_sale_date: str
    is_active: bool


class ProductPage(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[Product]


def load_catalog(path: Path) -> dict[str, Product]:
    with open(path, encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            row["product_code"]: Product(
                product_code=row["product_code"],
                product_name=row["product_name"],
                category=row["category"],
                category_source=row["category_source"],
                supplier_country=row["supplier_country"] or None,
                list_price=float(row["list_price"]),
                last_sale_date=row["last_sale_date"],
                is_active=row["is_active"] == "True",
            )
            for row in rows
        }


app = FastAPI(title="DataMart - API de productos", version="1.0.0")
CATALOG = load_catalog(CATALOG_PATH)
ORDERED = sorted(CATALOG.values(), key=lambda p: p.product_code)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "products": len(CATALOG)}


@app.get("/products", response_model=ProductPage)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    category: str | None = Query(None, description="Filtra por categoría exacta"),
    is_active: bool | None = Query(None, description="true = activos, false = descontinuados"),
) -> ProductPage:
    items = [
        p for p in ORDERED
        if (category is None or p.category.lower() == category.lower())
        and (is_active is None or p.is_active == is_active)
    ]
    start = (page - 1) * page_size
    return ProductPage(
        page=page,
        page_size=page_size,
        total=len(items),
        total_pages=max(1, math.ceil(len(items) / page_size)),
        items=items[start : start + page_size],
    )


@app.get("/products/{product_code}", response_model=Product)
def get_product(product_code: str) -> Product:
    """El código se normaliza igual que en el ETL: mayúsculas y sin espacios."""
    key = re.sub(r"\s+", "", product_code).upper()
    product = CATALOG.get(key)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Producto {key!r} no existe en el catálogo")
    return product
