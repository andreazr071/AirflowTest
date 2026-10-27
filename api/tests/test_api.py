import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["products"] > 3000


def test_listado_paginado():
    first = client.get("/products", params={"page": 1, "page_size": 50}).json()
    assert len(first["items"]) == 50 and first["page"] == 1
    assert first["total_pages"] == -(-first["total"] // 50)
    last = client.get("/products", params={"page": first["total_pages"], "page_size": 50}).json()
    assert 0 < len(last["items"]) <= 50
    beyond = client.get("/products", params={"page": first["total_pages"] + 1, "page_size": 50}).json()
    assert beyond["items"] == []


def test_paginas_no_se_repiten_y_cubren_todo():
    codes, page = [], 1
    while True:
        body = client.get("/products", params={"page": page, "page_size": 1000}).json()
        codes += [p["product_code"] for p in body["items"]]
        if page >= body["total_pages"]:
            break
        page += 1
    assert len(codes) == len(set(codes)) == body["total"]


def test_filtros():
    inactive = client.get("/products", params={"is_active": False, "page_size": 1000}).json()
    assert inactive["total"] > 0 and all(not p["is_active"] for p in inactive["items"])
    stationery = client.get("/products", params={"category": "papelería", "page_size": 1000}).json()
    assert stationery["total"] > 0 and all(p["category"] == "Papelería" for p in stationery["items"])


def test_producto_por_codigo_normaliza():
    code = client.get("/products", params={"page_size": 1}).json()["items"][0]["product_code"]
    assert client.get(f"/products/{code.lower()}").json()["product_code"] == code
    assert client.get(f"/products/%20{code}%20").status_code == 200


def test_producto_inexistente_404():
    assert client.get("/products/NO-EXISTE").status_code == 404


def test_campos_requeridos():
    item = client.get("/products", params={"page_size": 1}).json()["items"][0]
    for field in ("product_code", "product_name", "category", "supplier_country", "is_active"):
        assert field in item
