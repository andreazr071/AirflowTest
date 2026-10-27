"""Perfil rápido de un CSV de origen (filas, vacíos, rangos, duplicados, casos ambiguos).
Uso:  PYTHONPATH=include python scripts/profile_sources.py data/raw/data.csv data_csv
      (segundo argumento: data_csv | online_retail_ii)"""
import sys

import pandas as pd

from datamart_etl import schemas as S
from datamart_etl.transform import normalize_code, read_source_csv


def main(path: str, system: str) -> None:
    spec = S.SOURCES[system]
    df = read_source_csv(path, spec)
    qty, price = pd.to_numeric(df["quantity"], errors="coerce"), pd.to_numeric(df["unit_price"], errors="coerce")
    code = normalize_code(df["stock_code"].str.strip())
    print(f"filas: {len(df):,}   columnas: {S.CANONICAL_COLUMNS}")
    print("vacíos por columna:", {c: int((df[c].str.strip() == '').sum()) for c in S.CANONICAL_COLUMNS})
    print(f"cantidad <= 0: {(qty <= 0).sum():,}   precio == 0: {(price == 0).sum():,}   precio < 0: {(price < 0).sum():,}")
    print(f"facturas con prefijo C: {df['invoice_no'].str.upper().str.startswith('C').sum():,}")
    print(f"códigos crudos: {df['stock_code'].nunique():,}   normalizados: {code.nunique():,}")
    print(f"códigos fuera del patrón de catálogo: {sorted(set(code[~code.str.fullmatch(S.CATALOG_CODE.pattern)]))[:20]}")
    print(f"duplicados exactos: {df.drop(columns='source_row_number').duplicated().sum():,}")
    desc = df['description'].str.strip()
    print(f"descripciones no en mayúsculas: {(desc != desc.str.upper()).sum():,}")
    print("países:", df["country"].nunique(), "| fechas (texto) ejemplo:", df["invoice_date"].iloc[0])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
