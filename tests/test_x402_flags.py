from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.x402_gate import (
    payment_flags_on,
    payment_requirements,
    verify_and_settle,
)


def _sig(nonce: str = "n1") -> str:
    payload = {"payload": {"authorization": {"from": "0xabc", "nonce": nonce, "value": "3000"}}}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_flags_off_reliable_still_free():
    assert payment_flags_on() is False
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 200
    assert r.json()["valid_final"] is True


def test_settle_skipped_when_flag_off():
    out = verify_and_settle("anything")
    assert out["settlement_status"] == "skipped_flag_off"
    assert out.get("is_real") is False
    assert out["tx_hash"] is None


def test_mock_402_without_signature(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 402
    assert "PAYMENT-REQUIRED" in r.headers
    body = r.json()
    assert body["x402Version"] == 2
    assert body["accepts"][0]["network"] == "eip155:8453"
    assert body["accepts"][0]["amount"] == "3000"


def test_mock_settle_is_not_real(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'}, headers={"PAYMENT-SIGNATURE": _sig("nonce-a")})
    assert r.status_code == 200
    assert r.headers.get("X-AJR-SETTLEMENT") == "MOCK_NOT_REAL"
    receipt = json.loads(base64.b64decode(r.headers["PAYMENT-RESPONSE"]))
    assert receipt["settlement_status"] == "mock_settled"
    assert receipt["is_real"] is False
    assert receipt["tx_hash"] is None
    r2 = client.post("/v1/json/reliable", json={"text": '{"a":1,}'}, headers={"PAYMENT-SIGNATURE": _sig("nonce-a")})
    assert r2.status_code == 402


def test_requirements_price_atomic():
    req = payment_requirements()
    assert req["x402Version"] == 2
    assert req["accepts"][0]["asset"].startswith("0x")
    assert "bazaar" in req["extensions"]
