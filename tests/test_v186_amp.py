"""V186 discovery amplifier. No payment. No spend. No window wait."""
from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.product_registry import PRODUCTS
from products.beta.store_catalog import select_products, validate_bazaar_metadata
from products.gateway.mcp_server import call_tool, mcp_tools


def test_bazaar_metadata_complete():
    assert validate_bazaar_metadata() == []
    assert len(PRODUCTS) == 24


def test_selector_top3_tasks():
    cases = {
        "compare two URLs": "evidence_compare",
        "check CORS": "url_cors_check",
        "validate x402 endpoint": "x402_preflight",
        "extract tables": "web_tables",
        "repair JSON": "json_reliable",
        "check OpenAPI breaking changes": "api_openapi_diff",
    }
    for task, top in cases.items():
        out = select_products(task)
        assert out["top"] == top
        assert out["llm_used"] is False
        assert 1 <= len(out["matches"]) <= 3
        m0 = out["matches"][0]
        assert m0["endpoint"].startswith("/v1/")
        assert m0["price"]
        assert m0["input_example"] is not None
        assert m0["reason"]


def test_skill_catalog_mcp_discovery(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://agent-json-reliability.onrender.com")
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    sk = client.get("/skill.md")
    assert sk.status_code == 200
    assert "https://agent-json-reliability.onrender.com/v1/catalog" in sk.text
    assert "localhost" not in sk.text
    cat = client.get("/v1/catalog")
    assert cat.status_code == 200
    assert cat.json()["product_count"] == 24
    p0 = cat.json()["products"][0]
    assert p0["output_schema"]
    assert p0["example_output"]
    sel = client.post("/v1/catalog/select", json={"task": "check CORS"})
    assert sel.json()["top"] == "url_cors_check"
    wk = client.get("/.well-known/agent.json").json()
    assert wk["skill"].startswith("https://")
    assert client.get("/.well-known/x402").json()["skill"].startswith("https://")
    names = {t["name"] for t in mcp_tools()}
    assert {"list_paid_products", "select_paid_product", "inspect_json"} <= names
    listed = call_tool("list_paid_products", {})
    assert listed["paid_work_executed"] is False
    assert listed["product_count"] == 24
    picked = call_tool("select_paid_product", {"task": "extract tables"})
    assert picked["top"] == "web_tables"
    assert picked["paid_work_executed"] is False
    rpc = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    rpc_names = {t["name"] for t in rpc.json()["result"]["tools"]}
    assert "list_paid_products" in rpc_names
    assert "select_paid_product" in rpc_names
