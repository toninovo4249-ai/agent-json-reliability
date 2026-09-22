"""V183 evidence paid 402 vs AJR isolation. No live spend."""
from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.x402_gate import payment_requirements


def test_ajr_price_unchanged_in_requirements():
    req = payment_requirements("/v1/json/reliable")
    assert req["accepts"][0]["amount"] == "3000"
    ev = payment_requirements("/v1/evidence/pack")
    assert ev["accepts"][0]["amount"] == "7500"
    assert ev["price_usdc"] in {"0.0075", 0.0075} or str(ev["price_usdc"]) == "0.0075"


def test_mock_evidence_402_and_ajr_distinct(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    ajr = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert ajr.status_code == 402
    assert ajr.json()["accepts"][0]["amount"] == "3000"
    ev = client.post("/v1/evidence/pack", json={"url": "https://example.com/"})
    assert ev.status_code == 402
    assert ev.json()["accepts"][0]["amount"] == "7500"
    inspect = client.post("/v1/json/inspect", json={"text": '{"a":1}'})
    assert inspect.status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/v1/json/reliable"]["post"]["x-payment-info"]["price"]["amount"] == "0.003"
    assert spec["paths"]["/v1/evidence/pack"]["post"]["x-payment-info"]["price"]["amount"] == "0.0075"
    wk = client.get("/.well-known/x402").json()
    assert any(r.endswith("/v1/json/reliable") for r in wk["resources"])
    assert any(r.endswith("/v1/evidence/pack") for r in wk["resources"])
    assert len(wk["resources"]) >= 2
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    names = {t["name"] for t in listed["result"]["tools"]}
    assert {"validate_json", "repair_json", "inspect_json", "reliable_json"} <= names
    sig = base64.b64encode(
        json.dumps({"payload": {"authorization": {"from": "0xabc", "nonce": "ev-1", "value": "7500"}}}).encode()
    ).decode()
    paid = client.post(
        "/v1/evidence/pack",
        json={"url": "https://example.com/"},
        headers={"PAYMENT-SIGNATURE": sig},
    )
    assert paid.status_code == 200
    assert paid.headers.get("X-AJR-SETTLEMENT") == "MOCK_NOT_REAL"
    assert paid.json().get("fresh_fetch") is True
