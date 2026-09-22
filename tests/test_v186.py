"""V186 traffic classifier and 402 Index window. No payment. No spend."""
from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.acquisition import acquisition_metrics, classify_event, directory_sweep_hashes
from products.beta.app import create_json_beta_app
from products.beta.identity import traffic_class, traffic_kind
from products.beta.index_status import BATCH_LIMIT, counts, mark_pending_retry, next_submit_at, queue_ids, seed_v185
from products.beta.product_registry import PRODUCTS


def test_traffic_class_directory_and_synthetic():
    assert traffic_kind({"user-agent": "x402scan-bot/1"}, "x402scan-bot/1", "1.2.3.4", "/v1/json/reliable") == "DIRECTORY_PROBE"
    assert traffic_class("DIRECTORY_PROBE") == "DIRECTORY_PROBE"
    assert traffic_kind({"user-agent": "402index crawler"}, "402index crawler", "1.2.3.4", "/v1/web/extract") == "DIRECTORY_PROBE"
    assert traffic_kind({}, "Googlebot/2.1", "1.2.3.4", "/v1/catalog") == "SEARCH_CRAWLER"
    assert traffic_class("SEARCH_CRAWLER") == "SEARCH_CRAWLER"
    assert traffic_kind({"x-synthetic-buyer": "1"}, "Mozilla/5.0", "8.8.8.8", "/v1/json/reliable") == "SYNTHETIC"
    assert traffic_kind({}, "cursor/1.0", "8.8.8.8", "/v1/json/reliable") == "SYNTHETIC"
    assert traffic_kind({}, "x402-hunter-v186", "8.8.8.8", "/health") == "SYNTHETIC"
    assert traffic_kind({}, "SomeAgent/1.0", "8.8.8.8", "/v1/json/reliable") == "REAL_EXTERNAL_AGENT"
    assert traffic_kind({}, "SomeAgent/1.0", "8.8.8.8", "/v1/json/reliable", source="x402scan") == "DIRECTORY_PROBE"
    assert traffic_class("REAL_EXTERNAL_UNKNOWN") == "REAL_EXTERNAL_AGENT"


def test_acquisition_excludes_directory_and_sweep(monkeypatch):
    paid = {p["path"] for p in PRODUCTS}
    rows = []
    for i, p in enumerate(PRODUCTS):
        rows.append(
            {
                "endpoint": p["path"],
                "http_status": 402,
                "traffic_kind": "REAL_EXTERNAL_UNKNOWN",
                "anonymous_client_hash": "indexer",
                "probe_class": None,
                "self_reported_source": None,
            }
        )
    rows.append(
        {
            "endpoint": "/v1/json/reliable",
            "http_status": 402,
            "traffic_kind": "REAL_EXTERNAL_UNKNOWN",
            "anonymous_client_hash": "lonely-buyer",
            "probe_class": None,
            "self_reported_source": None,
        }
    )
    rows.append(
        {
            "endpoint": "/v1/json/reliable",
            "http_status": 402,
            "traffic_kind": "DIRECTORY_PROBE",
            "anonymous_client_hash": "scan",
            "probe_class": None,
        }
    )
    sweep = directory_sweep_hashes(rows, paid)
    assert "indexer" in sweep
    assert classify_event(rows[0], sweep) == "DIRECTORY_PROBE"
    assert classify_event(rows[-2], sweep) == "REAL_EXTERNAL_AGENT"
    m = acquisition_metrics(rows)
    assert m["DIRECTORY_402_PROBES"] >= 24
    assert m["REAL_EXTERNAL_402_CALLS"] == 1
    assert m["PAYMENT_ATTEMPTS"] == 0


def test_402index_queue_no_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr("products.beta.index_status.STATUS_FILE", tmp_path / "402index_status.json")
    data = seed_v185()
    c = counts(data)
    assert c["SUBMITTED_PENDING"] == 4
    assert c["RATE_LIMITED"] == 6
    assert c["NOT_SUBMITTED"] == 14
    q = queue_ids(data, 10)
    assert len(q) == 10
    assert len(set(q)) == 10
    assert "json_reliable" not in q
    marked = mark_pending_retry(data, next_submit_at(data), "hourly_cap_no_wait")
    assert len(marked) == 20
    assert data["earliest_retry_at"]
    c2 = counts(data)
    assert c2["PENDING_RETRY"] == 20
    assert c2["SUBMITTED_PENDING"] == 4
    assert c2["NOT_SUBMITTED"] == 0


def test_directory_probe_skips_app_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    monkeypatch.setattr("products.beta.app.MAX_REQUESTS_PER_MINUTE_PER_SESSION", 3)
    client = TestClient(create_json_beta_app())
    codes = []
    for _ in range(8):
        r = client.post("/v1/json/reliable", json={"text": "{'a':1}"}, headers={"User-Agent": "x402scan-indexer/1"})
        codes.append(r.status_code)
    assert codes.count(402) == 8
    assert 429 not in codes
    paid = client.post(
        "/v1/json/reliable",
        json={"text": "{'a':1}"},
        headers={"User-Agent": "x402scan-indexer/1", "PAYMENT-SIGNATURE": "not-a-real-sig"},
    )
    assert paid.status_code != 200
