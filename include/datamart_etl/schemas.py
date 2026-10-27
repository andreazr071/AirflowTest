"""Contratos de datos: columnas canónicas, alias por fuente, reglas de rechazo y clave de duplicado.

Todo lo que es decisión de negocio vive aquí o en transform.py de forma explícita,
para poder leerlo sin ejecutar el código (ver docs/DECISIONES_TECNICAS.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CANONICAL_COLUMNS = [
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]

# Los dos CSV nombran distinto las mismas columnas (InvoiceNo/Invoice, UnitPrice/Price,
# CustomerID/"Customer ID"). Se comparan sin mayúsculas ni signos para tolerar variantes.
HEADER_ALIASES = {
    "invoiceno": "invoice_no",
    "invoice": "invoice_no",
    "stockcode": "stock_code",
    "description": "description",
    "quantity": "quantity",
    "invoicedate": "invoice_date",
    "unitprice": "unit_price",
    "price": "unit_price",
    "customerid": "customer_id",
    "country": "country",
}


def canonical_header(raw_header: str) -> str | None:
    return HEADER_ALIASES.get(re.sub(r"[^a-z0-9]", "", raw_header.lower()))


@dataclass(frozen=True)
class SourceSpec:
    system: str  # valor que queda en la columna source_system
    priority: int  # 1 = gana en caso de duplicado entre fuentes
    date_formats: tuple[str, ...]  # formatos aceptados, en orden de intento
    encodings: tuple[str, ...]
    description: str
    required: bool = True  # False: si el archivo no existe, la fuente se omite sin fallar


SALES_DAILY = SourceSpec(
    system="data_csv",
    priority=1,
    date_formats=("%m/%d/%Y %H:%M",),
    encodings=("utf-8-sig", "latin-1"),  # data.csv de Kaggle viene en latin-1 (símbolo £)
    description="Volcado diario de órdenes (carrie1/ecommerce-data, data.csv)",
)
HISTORY = SourceSpec(
    system="online_retail_ii",
    priority=2,
    date_formats=("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"),
    encodings=("utf-8-sig", "latin-1"),
    description="Historial extendido (online_retail_II.csv), opcional",
    required=False,
)
SOURCES = {SALES_DAILY.system: SALES_DAILY, HISTORY.system: HISTORY}

# Un registro es "el mismo hecho" en ambas fuentes si coinciden TODOS estos campos.
DEDUP_KEY = [
    "invoice_no",
    "product_code",
    "invoice_ts_utc",
    "quantity",
    "unit_price",
    "customer_id",
    "country",
]

# Motivos de rechazo (si varios aplican, gana el primero de esta lista).
REJECT_MISSING_INVOICE = "FACTURA_FALTANTE"
REJECT_MISSING_CODE = "CODIGO_PRODUCTO_FALTANTE"
REJECT_BAD_DATE = "FECHA_INVALIDA"
REJECT_BAD_QUANTITY = "CANTIDAD_INVALIDA"
REJECT_BAD_PRICE = "PRECIO_INVALIDO"
REJECT_BAD_CUSTOMER = "CUSTOMER_ID_INVALIDO"
REJECT_SALE_NON_POSITIVE_PRICE = "PRECIO_NO_POSITIVO_EN_VENTA"
REJECT_RETURN_NEGATIVE_PRICE = "PRECIO_NEGATIVO_EN_DEVOLUCION"
REJECT_EXACT_DUPLICATE = "DUPLICADO_EXACTO_EN_FUENTE"

# Códigos que no son mercancía (fletes, comisiones, descuentos, ajustes, bonos regalo).
NON_MERCHANDISE_CODE = re.compile(
    r"POST|DOT|M|C2|D|S|B|BANKCHARGES|AMAZONFEE|CRUK|ADJUST\d*|TEST\d+|GIFT_.*"
)
CATALOG_CODE = re.compile(r"\d{5}[A-Z]{0,2}")  # patrón del catálogo: 85123A, 22423

COUNTRY_ALIASES = {"EIRE": "Ireland", "RSA": "South Africa", "USA": "United States"}

CATEGORY_NON_MERCHANDISE = "No producto"
CATEGORY_UNCLASSIFIED = "Sin clasificar"
CATEGORY_DEFAULT = "Hogar"
