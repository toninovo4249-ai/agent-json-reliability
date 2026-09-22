from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.x402_gate import valid_seller_receive_address


def test_seller_address_format_only():
    assert valid_seller_receive_address("0x" + "ab" * 20) is True
    assert valid_seller_receive_address("0x" + "AB" * 20) is True
    assert valid_seller_receive_address("") is False
    assert valid_seller_receive_address("not-an-address") is False
    assert valid_seller_receive_address("0x123") is False


def test_flags_off_free_routes_and_reliable(monkeypatch, tmp_path):
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    assert client.post("/v1/json/inspect", json={"text": '{"a":1}'}).status_code == 200
    assert client.post("/v1/json/reliable", json={"text": '{"a":1,}'}).status_code == 200
    h = client.get("/health").json()
    assert h["X402_PAYMENT_ENABLED"] is False
    assert h["REAL_PAID_CALLS"] == 0
    assert h["REAL_REVENUE_USDC"] == 0


def test_paid_flags_on_without_seller_is_503_not_free(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("MAINNET_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "")
    monkeypatch.setenv("CDP_API_KEY_ID", "id")
    monkeypatch.setenv("CDP_API_KEY_SECRET", "c2VjcmV0")
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 503
    assert r.json()["error"] == "payment_misconfigured"
    assert "seller_receive_address_invalid_or_missing" in r.json()["blockers"]
    assert client.post("/v1/json/inspect", json={"text": '{"a":1}'}).status_code == 200


def test_paid_flags_on_mainnet_without_cdp_secret_is_503(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("MAINNET_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("CDP_API_KEY_ID", "id-only")
    monkeypatch.delenv("CDP_API_KEY_SECRET", raising=False)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 503
    assert "cdp_facilitator_auth_missing" in r.json()["blockers"]


def test_invalid_price_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("X402_PRICE_ATOMIC", "9999")
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 503
    assert "invalid_price" in r.json()["blockers"]
