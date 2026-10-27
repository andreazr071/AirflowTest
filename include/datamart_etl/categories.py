"""Asignación de categoría de producto.

Orden de prioridad: (1) categoría de la API interna de productos (sección 4.3, servicio `products-api`)
cuando está configurada y el código existe en su catálogo; (2) reglas de palabras clave como respaldo;
(3) categoría por defecto. Si la API no está configurada, el flujo usa solo las reglas.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import schemas as S

DEFAULT_RULES_PATH = Path(__file__).parent / "reference" / "category_rules.csv"


@dataclass(frozen=True)
class Rule:
    priority: int  # menor = se evalúa primero
    category: str
    keyword: str
    pattern: re.Pattern


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> list[Rule]:
    """Lee priority,category,keyword. La palabra clave coincide como palabra completa (con plural en S)."""
    rules: list[Rule] = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            keyword = row["keyword"].strip().upper()
            pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(keyword)}S?(?![A-Z0-9])")
            rules.append(Rule(int(row["priority"]), row["category"].strip(), keyword, pattern))
    # sorted es estable: a igual prioridad manda el orden del archivo
    return sorted(rules, key=lambda rule: rule.priority)


def assign_categories(
    products: pd.DataFrame, rules: list[Rule], api_categories: dict[str, str] | None = None
) -> pd.DataFrame:
    """Agrega `category` y `category_source` a dim_product.

    - Código que no es mercancía (POST, M, D, bonos...) -> "No producto".
    - Mercancía sin nombre -> "Sin clasificar".
    - Código con categoría en la API (`api_categories`: código -> categoría) -> esa categoría, `category_source = api`.
    - Primera regla (por prioridad) cuya palabra aparece en el nombre canónico.
    - Sin coincidencia -> categoría por defecto "Hogar" (el catálogo es mayoritariamente
      decoración y regalos); queda marcada como `default` para poder medir su peso.
    """
    result = products.copy()
    result["category"] = None
    result["category_source"] = None

    non_merch = ~result["is_merchandise"]
    result.loc[non_merch, ["category", "category_source"]] = [S.CATEGORY_NON_MERCHANDISE, "no_producto"]

    unnamed = result["is_merchandise"] & result["product_name"].isna()
    result.loc[unnamed, ["category", "category_source"]] = [S.CATEGORY_UNCLASSIFIED, "sin_nombre"]

    if api_categories:
        from_api = result["product_code"].map(api_categories)
        pending = result["category"].isna() & from_api.notna()
        result.loc[pending, "category"] = from_api[pending]
        result.loc[pending, "category_source"] = "api"

    names = result["product_name"].fillna("")
    for rule in rules:
        pending = result["category"].isna() & names.str.contains(rule.pattern, regex=True)
        result.loc[pending, "category"] = rule.category
        result.loc[pending, "category_source"] = f"regla:{rule.keyword}"

    still_open = result["category"].isna()
    result.loc[still_open, ["category", "category_source"]] = [S.CATEGORY_DEFAULT, "default"]
    return result
