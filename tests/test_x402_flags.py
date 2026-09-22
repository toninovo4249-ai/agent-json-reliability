from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.x402_gate import payment_flags_on, verify_and_settle


def test_flags_off_reliable_still_free():
    assert payment_flags_on() is False
    client = TestClient(create_json_beta_app())
    r = client.post("/v1/json/reliable", json={"text": '{"a":1,}'})
    assert r.status_code == 200
    assert r.json()["valid_final"] is True
    h = client.get("/health").json()
    assert h["X402_PAYMENT_ENABLED"] is False
    assert h["x402_middleware_present"] is True


def test_settle_skipped_when_flag_off():
    out = verify_and_settle("anything")
    assert out["settlement_status"] == "skipped_flag_off"
    assert out["tx_hash"] is None


def test_maybe_payment_none_when_disabled():
    client = TestClient(create_json_beta_app())
    # middleware still serves inspect free
    r = client.post("/v1/json/inspect", json={"text": '{"a":1}'})
    assert r.status_code == 200
