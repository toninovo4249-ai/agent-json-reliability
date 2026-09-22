"""V185 free catalog + select. No payment. No spend."""
from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.product_registry import PRODUCTS
from products.beta.store_catalog import select_products


def test_catalog_and_select_free(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    monkeypatch.setattr("products.beta.app.MAX_REQUESTS_PER_MINUTE_PER_SESSION", 10000)
    client = TestClient(create_json_beta_app())
    cat = client.get("/v1/catalog")
    assert cat.status_code == 200
    data = cat.json()
    assert data["product_count"] == 24
    assert len(data["products"]) == 24
    ids = {p["product_id"] for p in data["products"]}
    assert ids == {p["id"] for p in PRODUCTS}
    for p in data["products"]:
        assert p["method"] == "POST"
        assert p["x402"] is True
        assert p["use_when"]
        assert p["input_schema"]["type"] == "object"
        assert p["keywords"]
    assert client.get("/.well-known/agent-products.json").status_code == 200
    assert client.get("/products").status_code == 200
    s1 = client.post("/v1/catalog/select", json={"task": "fix malformed JSON"})
    assert s1.status_code == 200
    assert s1.json()["top"] == "json_reliable"
    s2 = client.post("/v1/catalog/select", json={"task": "compare two web sources"})
    assert s2.json()["top"] == "evidence_compare"
    s3 = client.post("/v1/catalog/select", json={"task": "check x402 endpoint"})
    assert s3.json()["top"] == "x402_preflight"
    spec = client.get("/openapi.json").json()
    for p in PRODUCTS:
        op = spec["paths"][p["path"]]["post"]
        assert op["x-payment-info"]["price"]["amount"] == str(p["price_usdc"])
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert schema.get("type") == "object"
    sm = client.get("/sitemap.xml").text
    assert "/v1/catalog" in sm
    assert "/.well-known/agent-products.json" in sm
    llms = client.get("/llms.txt").text
    assert "/v1/catalog" in llms
    agents = client.get("/AGENTS.md").text
    assert "/v1/catalog/select" in agents
    inspect = client.post("/v1/json/inspect", json={"text": '{"a":1}'})
    assert inspect.status_code == 200
    ajr = client.post("/v1/json/reliable", json={"text": "{'a':1}"})
    assert ajr.status_code == 402
    assert ajr.json()["accepts"][0]["amount"] == "3000"


def test_select_tables():
    assert select_products("extract html tables")["top"] == "web_tables"
