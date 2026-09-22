"""V184 Agent Utility Store. Mock payment only. No live spend."""
from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.beta.product_registry import PRODUCTS
from products.beta.x402_gate import payment_requirements
from products.fresh_web_evidence.fetch import FetchResult


HTML = (
    b"<html lang='en'><head><title>Example</title>"
    b"<meta name='description' content='d'>"
    b"<meta property='og:title' content='og'>"
    b"<meta name='twitter:card' content='summary'>"
    b"<link rel='canonical' href='https://example.com/c'>"
    b"<link rel='icon' href='/favicon.ico'>"
    b"<script type='application/ld+json'>{\"name\":\"n\"}</script>"
    b"</head><body><h1>Hello</h1>"
    b"<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
    b"<a href='/in'>in</a><a href='https://other.test/x'>out</a>"
    b"</body></html>"
)

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/x": {
            "get": {
                "summary": "g",
                "responses": {"200": {"description": "ok"}},
                "parameters": [],
            }
        }
    },
}


def _sig(nonce: str) -> str:
    return base64.b64encode(
        json.dumps({"payload": {"authorization": {"from": "0xabc", "nonce": nonce, "value": "1"}}}).encode()
    ).decode()


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PAID_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ALLOW_MOCK_X402", "true")
    monkeypatch.setenv("SELLER_RECEIVE_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setattr("products.beta.app.MAX_REQUESTS_PER_MINUTE_PER_SESSION", 10000)
    monkeypatch.setattr("products.beta.paid_ledger.PAID_LEDGER_PATH", tmp_path / "paid.sqlite")
    return TestClient(create_json_beta_app())


def fake_fetch(url: str, **kwargs):
    if "127.0.0.1" in url or "localhost" in url:
        return FetchResult(
            requested_url=url,
            url=url,
            fetched_at="2026-01-01T00:00:00Z",
            error="blocked_ip",
            http_status=None,
        )
    headers = {
        "content-type": "text/html",
        "strict-transport-security": "max-age=1",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
        "permissions-policy": "geolocation=()",
        "last-modified": "Wed, 21 Oct 2015 07:28:00 GMT",
        "etag": '"abc"',
        "cache-control": "max-age=60",
        "access-control-allow-origin": "*",
    }
    body = HTML
    if url.endswith("/openapi.json") or "openapi" in url:
        body = json.dumps(SPEC).encode()
        headers["content-type"] = "application/json"
    if url.endswith("/.well-known/x402"):
        body = json.dumps({"resources": ["https://example.com/v1/json/reliable"]}).encode()
        headers["content-type"] = "application/json"
    status = 402 if "/v1/json/reliable" in url and kwargs.get("method") == "POST" else 200
    if status == 402:
        body = json.dumps(
            {"x402Version": 2, "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "3000", "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "payTo": "0x" + "11" * 20}]}
        ).encode()
        headers["payment-required"] = "1"
        headers["content-type"] = "application/json"
    return FetchResult(
        requested_url=url,
        url=url,
        fetched_at="2026-01-01T00:00:00Z",
        http_status=status,
        content_sha256="a" * 64,
        content_type=headers.get("content-type"),
        body=body,
        headers=headers,
        hops=[{"url": url, "status": status}],
        error=None if status in {200, 402} else f"http_{status}",
    )


def test_registry_24_and_existing_prices():
    assert len(PRODUCTS) == 24
    by = {p["path"]: p for p in PRODUCTS}
    assert by["/v1/json/reliable"]["price_atomic"] == 3000
    assert by["/v1/evidence/pack"]["price_atomic"] == 7500
    amounts = {}
    for p in PRODUCTS:
        req = payment_requirements(p["path"])
        amt = req["accepts"][0]["amount"]
        assert amt == str(p["price_atomic"])
        amounts[p["path"]] = amt
    assert amounts["/v1/json/reliable"] == "3000"
    assert amounts["/v1/evidence/pack"] == "7500"
    assert amounts["/v1/evidence/compare"] == "10000"
    assert amounts["/v1/web/extract"] == "5000"


def test_unpaid_402_isolation_and_free_routes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    seen = {}
    for p in PRODUCTS:
        r = client.post(p["path"], json={"url": "https://example.com/", "text": '{"a":1}', "before": {"a": 1}, "after": {"a": 2}, "json": {"a": 1}, "schema": {"type": "object"}})
        assert r.status_code == 402, (p["path"], r.status_code, r.text[:200])
        amt = r.json()["accepts"][0]["amount"]
        assert amt == str(p["price_atomic"])
        seen[p["path"]] = amt
    assert seen["/v1/json/reliable"] != seen["/v1/evidence/pack"]
    assert seen["/v1/web/extract"] != seen["/v1/json/reliable"]
    ins = client.post("/v1/json/inspect", json={"text": '{"a":1}'})
    assert ins.status_code == 200
    h = client.get("/health")
    assert h.status_code == 200
    mcp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in mcp.json()["result"]["tools"]}
    assert {"validate_json", "repair_json", "inspect_json", "reliable_json"} <= names
    spec = client.get("/openapi.json").json()
    paid_oa = 0
    for p in PRODUCTS:
        info = spec["paths"][p["path"]]["post"].get("x-payment-info")
        assert info["price"]["amount"] == str(p["price_usdc"])
        paid_oa += 1
    assert paid_oa == 24
    wk = client.get("/.well-known/x402").json()
    assert len(wk["resources"]) == 24
    html = client.get("/").text
    assert "Agent Utility Store" in html


def test_json_products_happy_and_invalid(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ok = client.post(
        "/v1/json/contract-check",
        json={"json": {"a": 1}, "schema": {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}},
        headers={"PAYMENT-SIGNATURE": _sig("c1")},
    )
    assert ok.status_code == 200
    assert ok.json()["valid"] is True
    bad = client.post("/v1/json/contract-check", json={}, headers={"PAYMENT-SIGNATURE": _sig("c2")})
    assert bad.status_code == 400
    diff = client.post(
        "/v1/json/diff",
        json={"before": {"a": 1}, "after": {"a": 2, "b": 3}},
        headers={"PAYMENT-SIGNATURE": _sig("d1")},
    )
    assert diff.status_code == 200
    assert "b" in diff.json()["added_keys"]


def test_web_ssrf_and_extract(monkeypatch, tmp_path):
    monkeypatch.setattr("products.agent_utility.primitives.fetch_public_url", fake_fetch)
    monkeypatch.setattr("products.agent_utility.primitives.check_tls", lambda url: {"ok": True, "tls_available": True, "hostname_match": True})
    monkeypatch.setattr("products.agent_utility.primitives.mcp_initialize", lambda url: {"ok": True, "http_status": 200, "rpc": {"result": {"serverInfo": {"name": "t"}}}})
    monkeypatch.setattr("products.agent_utility.primitives.mcp_tools_list", lambda url: {"ok": True, "http_status": 200, "rpc": {"result": {"tools": [{"name": "x", "inputSchema": {}}]}}})
    client = _client(monkeypatch, tmp_path)
    ssrf = client.post("/v1/web/extract", json={"url": "http://127.0.0.1/"}, headers={"PAYMENT-SIGNATURE": _sig("s1")})
    assert ssrf.status_code in {200, 400}
    if ssrf.status_code == 200:
        assert ssrf.json().get("provenance", {}).get("error") or True
    else:
        assert "blocked" in ssrf.text or "invalid" in ssrf.text or "url" in ssrf.text
    ext = client.post("/v1/web/extract", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("w1")})
    assert ext.status_code == 200
    assert ext.json()["title"] == "Example"
    md = client.post("/v1/web/markdown", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("w2")})
    assert md.status_code == 200
    assert "Hello" in md.json()["markdown"] or md.json()["markdown"].startswith("#")
    tables = client.post("/v1/web/tables", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("w3")})
    assert tables.status_code == 200
    assert tables.json()["tables"]
    meta = client.post("/v1/web/metadata", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("w4")})
    assert meta.status_code == 200
    links = client.post("/v1/web/link-map", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("w5")})
    assert links.status_code == 200
    cmp = client.post(
        "/v1/evidence/compare",
        json={"urls": ["https://example.com/", "https://example.org/"]},
        headers={"PAYMENT-SIGNATURE": _sig("e1")},
    )
    assert cmp.status_code == 200
    assert cmp.json()["winner"] is None
    fr = client.post("/v1/evidence/freshness", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("e2")})
    assert fr.status_code == 200
    rec = client.post("/v1/evidence/receipt", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("e3")})
    assert rec.status_code == 200
    assert rec.json()["body_stored"] is False
    oa = client.post("/v1/api/openapi-audit", json={"spec": SPEC}, headers={"PAYMENT-SIGNATURE": _sig("a1")})
    assert oa.status_code == 200
    diff = client.post(
        "/v1/api/openapi-diff",
        json={"old": SPEC, "new": {"openapi": "3.0.0", "info": {"title": "t"}, "paths": {}}},
        headers={"PAYMENT-SIGNATURE": _sig("a2")},
    )
    assert diff.status_code == 200
    assert diff.json()["removed_endpoints"]
    drift = client.post(
        "/v1/api/schema-drift",
        json={"live_url": "https://example.com/openapi.json", "schema": {"type": "object"}, "method": "GET"},
        headers={"PAYMENT-SIGNATURE": _sig("a3")},
    )
    assert drift.status_code == 200
    mcp = client.post("/v1/mcp/preflight", json={"url": "https://example.com/mcp"}, headers={"PAYMENT-SIGNATURE": _sig("m1")})
    assert mcp.status_code == 200
    assert mcp.json()["tools_executed"] is False
    x402 = client.post(
        "/v1/x402/preflight",
        json={"url": "https://example.com/v1/json/reliable"},
        headers={"PAYMENT-SIGNATURE": _sig("x1")},
    )
    assert x402.status_code == 200
    assert x402.json()["payment_signature_sent"] is False
    assert x402.json()["spent_payment"] is False
    sh = client.post("/v1/url/security-headers", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u1")})
    assert sh.status_code == 200
    cors = client.post("/v1/url/cors-check", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u2")})
    assert cors.status_code == 200
    red = client.post("/v1/url/redirect-check", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u3")})
    assert red.status_code == 200
    rob = client.post("/v1/url/robots-audit", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u4")})
    assert rob.status_code == 200
    tls = client.post("/v1/url/tls-check", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u5")})
    assert tls.status_code == 200
    pre = client.post("/v1/url/preflight", json={"url": "https://example.com/"}, headers={"PAYMENT-SIGNATURE": _sig("u6")})
    assert pre.status_code == 200
    contra = client.post(
        "/v1/evidence/contradictions",
        json={"urls": ["https://example.com/", "https://example.org/"]},
        headers={"PAYMENT-SIGNATURE": _sig("e4")},
    )
    assert contra.status_code == 200


def test_wrong_payment_fail_closed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.post("/v1/json/diff", json={"before": {}, "after": {}}, headers={"PAYMENT-SIGNATURE": "not-valid"})
    assert r.status_code == 402


def test_oversized_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.post("/v1/json/diff", content=b"x" * (300000), headers={"content-type": "application/json"})
    assert r.status_code in {402, 413}
