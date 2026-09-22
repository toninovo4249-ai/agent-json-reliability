"""V181 Fresh Web Evidence Pack benchmarks. No live paid APIs."""
from __future__ import annotations

from fastapi.testclient import TestClient

from products.beta.app import create_json_beta_app
from products.fresh_web_evidence.extract import extract_claims, facts_from_claims
from products.fresh_web_evidence.fetch import FetchResult, fetch_url
from products.fresh_web_evidence.pack import build_pack
from products.fresh_web_evidence.ssrf import SsrfError, parse_public_http_url


def _fr(url: str, html: bytes, status: int = 200, ctype: str = "text/html") -> FetchResult:
    import hashlib

    return FetchResult(
        requested_url=url,
        url=url,
        fetched_at="2026-09-22T12:00:00Z",
        http_status=status,
        content_sha256=hashlib.sha256(html).hexdigest(),
        content_type=ctype,
        body=html if status == 200 else b"",
    )


ARTICLE_A = b"""<!doctype html><html><head>
<title>Widget 9</title>
<meta name="description" content="A widget">
<meta property="og:title" content="Widget 9">
<link rel="canonical" href="https://a.example/w">
<script type="application/ld+json">{"@type":"Product","name":"Widget","offers":{"price":"9.00","priceCurrency":"USD"}}</script>
</head><body><p>ok</p></body></html>"""

ARTICLE_B_AGREE = b"""<!doctype html><html><head>
<title>Widget 9</title>
<meta property="og:title" content="Widget 9">
<script type="application/ld+json">{"@type":"Product","name":"Widget","offers":{"price":"9.00","priceCurrency":"USD"}}</script>
</head></html>"""

ARTICLE_B_CONFLICT = b"""<!doctype html><html><head>
<title>Widget 12</title>
<meta property="og:title" content="Widget 12">
<script type="application/ld+json">{"@type":"Product","name":"Widget","offers":{"price":"12.00","priceCurrency":"USD"}}</script>
</head></html>"""


def test_single_clean_article():
    pack = build_pack({"url": "https://a.example/w"}, fetch_fn=lambda u: _fr(u, ARTICLE_A))
    assert pack["fresh_fetch"] is True
    assert pack["llm_used"] is False
    assert pack["paid_upstream_used"] is False
    assert pack["sources"][0]["fetched_at"].endswith("Z") or "T" in pack["sources"][0]["fetched_at"]
    assert pack["sources"][0]["content_sha256"]
    assert any(f["key"] == "html.title" for f in pack["facts"])
    for f in pack["facts"]:
        assert f["source_indexes"]
        assert f["source_urls"]


def test_two_agreeing_sources():
    table = {"https://a.example/1": ARTICLE_A, "https://b.example/1": ARTICLE_B_AGREE}

    pack = build_pack({"urls": list(table)}, fetch_fn=lambda u: _fr(u, table[u]))
    assert pack["contradictions"] == []
    price = [f for f in pack["facts"] if f["key"].endswith("price") and f["value"] == "9.00"]
    assert price
    assert len(price[0]["source_indexes"]) == 2


def test_two_conflicting_sources():
    table = {"https://a.example/1": ARTICLE_A, "https://b.example/1": ARTICLE_B_CONFLICT}
    pack = build_pack({"urls": list(table)}, fetch_fn=lambda u: _fr(u, table[u]))
    assert pack["contradictions"]
    for c in pack["contradictions"]:
        assert c["winner"] is None
        assert len(c["values"]) >= 2


def test_redirect():
    hops = {"https://a.example/go": True}

    def transport(url, timeout, max_bytes, method):
        if url.endswith("robots.txt"):
            return 404, {}, b"", False
        if url.endswith("/go"):
            return 302, {"location": "https://a.example/ok"}, b"", False
        return 200, {"content-type": "text/html"}, b"<html><title>Landed</title></html>", False

    fr = fetch_url("https://a.example/go", check_robots=True, _transport=transport)
    assert fr.http_status == 200
    assert fr.url.endswith("/ok")
    claims = extract_claims(fr, 0)
    assert any(c["value"] == "Landed" for c in claims)


def test_timeout():
    pack = build_pack(
        {"url": "https://slow.example/x"},
        fetch_fn=lambda u: FetchResult(requested_url=u, url=u, fetched_at="2026-09-22T12:00:00Z", error="timeout"),
    )
    assert pack["sources"][0]["error"] == "timeout"
    assert any("timeout" in w for w in pack["warnings"])


def test_invalid_url():
    fr = fetch_url("not-a-url")
    assert fr.error == "non_http_scheme"
    try:
        build_pack({})
        assert False
    except ValueError as e:
        assert str(e) == "url_or_urls_required"


def test_ssrf_attempts():
    blocked = [
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ]
    for u in blocked:
        try:
            parse_public_http_url(u)
            raise AssertionError(u)
        except SsrfError:
            pass
        fr = fetch_url(u)
        assert fr.error


def test_oversized_response():
    def transport(url, timeout, max_bytes, method):
        if url.endswith("robots.txt"):
            return 404, {}, b"", False
        return 200, {"content-type": "text/html", "content-length": "999999"}, b"<html><title>Big</title></html>" + b"x" * 100, True

    fr = fetch_url("https://a.example/big", _transport=transport)
    assert fr.truncated is True


def test_non_html_json_ok_and_image_rejected():
    pack = build_pack(
        {"url": "https://a.example/p.json"},
        fetch_fn=lambda u: _fr(u, b'{"name":"n","price":1}', ctype="application/json"),
    )
    assert any(f["key"] == "json.name" for f in pack["facts"])

    def transport(url, timeout, max_bytes, method):
        if url.endswith("robots.txt"):
            return 404, {}, b"", False
        return 200, {"content-type": "image/png"}, b"\x89PNG", False

    fr = fetch_url("https://a.example/x.png", _transport=transport)
    assert fr.error == "unsupported_content_type"


def test_http_endpoint_and_ajr_unchanged():
    client = TestClient(create_json_beta_app())
    spec = client.get("/openapi.json").json()
    reliable = spec["paths"]["/v1/json/reliable"]["post"]
    assert reliable["x-payment-info"]["price"]["amount"] == "0.003"
    ev = spec["paths"]["/v1/evidence/pack"]["post"]
    assert "x-payment-info" not in ev
    wk = client.get("/.well-known/x402").json()
    assert isinstance(wk.get("resources"), list)
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    names = {t["name"] for t in listed["result"]["tools"]}
    assert {"validate_json", "repair_json", "inspect_json", "reliable_json"} <= names
    assert "evidence_pack" not in names
    r = client.post("/v1/evidence/pack", json={"urls": ["a"] * 6})
    assert r.status_code == 400
    ssrf = client.post("/v1/evidence/pack", json={"url": "http://127.0.0.1/"})
    assert ssrf.status_code == 200
    assert ssrf.json()["sources"][0].get("error")
    health = client.get("/health").json()
    assert "fresh_web_evidence" in health
    assert health["fresh_web_evidence"]["PAYMENT_ENABLED"] is False
    assert "REAL_PAID_CALLS" in health
    pos = client.post("/v1/json/inspect", json={"text": '{"a":1}'})
    assert pos.status_code == 200


def test_provenance_timestamp_sha_units():
    pack = build_pack({"url": "https://a.example/w"}, fetch_fn=lambda u: _fr(u, ARTICLE_A))
    src = pack["sources"][0]
    assert src["fetched_at"]
    assert len(src["content_sha256"]) == 64
    assert facts_from_claims(extract_claims(_fr("https://a.example/w", ARTICLE_A), 0))
