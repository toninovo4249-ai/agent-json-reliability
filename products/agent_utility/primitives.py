"""Shared deterministic primitives for the Agent Utility Store. No LLM. No paid APIs."""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse, urlunparse

from products.fresh_web_evidence.contradict import find_contradictions
from products.fresh_web_evidence.extract import extract_claims, facts_from_claims
from products.fresh_web_evidence.fetch import FetchResult, fetch_url
from products.fresh_web_evidence.robots import allowed_by_robots, robots_url_for
from products.fresh_web_evidence.ssrf import SsrfError, parse_public_http_url, resolve_public

MAX_URLS = 5
MAX_REDIRECTS = 5
SAFE_HTTP_METHODS = {"GET", "HEAD"}


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def content_sha256(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def ssrf_guard(url: str) -> tuple[str, str, str, int, str]:
    return parse_public_http_url(url)


def safe_dns_resolve(host: str) -> list[str]:
    return resolve_public(host)


def fetch_public_url(
    url: str,
    *,
    method: str = "GET",
    check_robots: bool = True,
    max_redirects: int = MAX_REDIRECTS,
    extra_headers: dict[str, str] | None = None,
    keep_error_body: bool = False,
    fetch_fn: Callable | None = None,
) -> FetchResult:
    fn = fetch_fn or fetch_url
    kwargs = {
        "method": method,
        "check_robots": check_robots,
        "max_redirects": max_redirects,
        "extra_headers": extra_headers,
        "keep_error_body": keep_error_body,
    }
    try:
        return fn(url, **kwargs)
    except TypeError:
        return fn(url)


def follow_redirects_safe(url: str, **kwargs) -> FetchResult:
    return fetch_public_url(url, **kwargs)


class _Page(HTMLParser):
    SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self._in_title = False
        self._skip = 0
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.headings: list[dict[str, str]] = []
        self._h_tag = ""
        self._h_buf: list[str] = []
        self.text_parts: list[str] = []
        self.ld_chunks: list[str] = []
        self._in_ld = False
        self._ld_buf: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.lang = ""
        self.favicon = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self._skip += 1
            return
        if tag == "html" and ad.get("lang"):
            self.lang = ad["lang"]
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            self.metas.append(ad)
        if tag == "link":
            self.links.append(ad)
            rel = (ad.get("rel") or "").lower()
            if "icon" in rel and ad.get("href"):
                self.favicon = ad["href"]
        if tag == "a" and ad.get("href"):
            self.anchors.append({"href": ad["href"], "rel": ad.get("rel") or ""})
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._h_tag = tag
            self._h_buf = []
        if tag == "script" and "ld+json" in (ad.get("type") or "").lower():
            self._in_ld = True
            self._ld_buf = []
        if tag == "table":
            self._table = []
        if tag == "tr" and self._table is not None:
            self._row = []
        if tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag == "title":
            self._in_title = False
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._h_tag:
            self.headings.append({"level": self._h_tag, "text": _ws("".join(self._h_buf))})
            self._h_tag = ""
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld_chunks.append("".join(self._ld_buf))
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_ws("".join(self._cell)))
            self._cell = None
        if tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._h_tag:
            self._h_buf.append(data)
        if self._in_ld:
            self._ld_buf.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if data.strip():
            self.text_parts.append(data)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_html(body: bytes) -> _Page:
    page = _Page()
    try:
        page.feed(body.decode("utf-8", "replace"))
        page.close()
    except Exception:
        pass
    return page


def extract_html_text(fr: FetchResult) -> dict[str, Any]:
    page = parse_html(fr.body or b"")
    title = _ws("".join(page.title_parts))
    text = _ws(" ".join(page.text_parts))[:20000]
    sections = [{"heading": h["text"], "level": h["level"]} for h in page.headings if h["text"]]
    return {"title": title, "text": text, "headings": page.headings, "sections": sections, "language": page.lang}


def extract_metadata(fr: FetchResult) -> dict[str, Any]:
    page = parse_html(fr.body or b"")
    meta: dict[str, Any] = {
        "title": _ws("".join(page.title_parts)),
        "description": "",
        "canonical": "",
        "language": page.lang,
        "favicon": page.favicon,
        "opengraph": {},
        "twitter": {},
        "json_ld": [],
    }
    for m in page.metas:
        name = (m.get("name") or m.get("property") or m.get("http-equiv") or "").lower()
        content = m.get("content") or ""
        if name == "description":
            meta["description"] = content
        if name.startswith("og:"):
            meta["opengraph"][name] = content
        if name.startswith("twitter:"):
            meta["twitter"][name] = content
        if name in {"content-language"} and not meta["language"]:
            meta["language"] = content
    for ln in page.links:
        rel = (ln.get("rel") or "").lower()
        if rel == "canonical" and ln.get("href"):
            meta["canonical"] = urljoin(fr.url, ln["href"])
    for chunk in page.ld_chunks[:10]:
        try:
            meta["json_ld"].append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return meta


def extract_links(fr: FetchResult) -> dict[str, Any]:
    page = parse_html(fr.body or b"")
    origin = urlparse(fr.url)
    internal: list[str] = []
    external: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for a in page.anchors:
        href = a["href"].strip()
        if href.startswith(("javascript:", "data:", "mailto:", "tel:")):
            invalid.append(href[:200])
            continue
        absu = urljoin(fr.url, href)
        try:
            p = urlparse(absu)
            canon = urlunparse((p.scheme, p.netloc.lower(), p.path or "/", "", p.query, ""))
        except Exception:
            invalid.append(href[:200])
            continue
        if canon in seen:
            continue
        seen.add(canon)
        if p.hostname and p.hostname.lower() == (origin.hostname or "").lower():
            internal.append(canon)
        else:
            external.append(canon)
    return {
        "internal": internal[:200],
        "external": external[:200],
        "invalid": invalid[:50],
        "counts": {
            "internal": len(internal),
            "external": len(external),
            "invalid": len(invalid),
        },
    }


def extract_tables(fr: FetchResult) -> list[dict[str, Any]]:
    page = parse_html(fr.body or b"")
    out = []
    for i, rows in enumerate(page.tables):
        if not rows:
            continue
        columns = rows[0]
        body = rows[1:] if len(rows) > 1 else []
        out.append({"index": i, "columns": columns, "rows": body[:200], "row_count": len(body), "source_index": 0})
    return out


def html_to_markdown(fr: FetchResult) -> str:
    extracted = extract_html_text(fr)
    lines = []
    if extracted["title"]:
        lines.append(f"# {extracted['title']}")
        lines.append("")
    for h in extracted["headings"]:
        n = int(h["level"][1]) if h["level"][1:].isdigit() else 2
        lines.append(f"{'#' * n} {h['text']}")
    if extracted["text"]:
        lines.append("")
        lines.append(extracted["text"][:15000])
    return "\n".join(lines).strip() + "\n"


def compare_sources(claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, dict[str, list[int]]] = {}
    for c in claims:
        by_key.setdefault(c["key"], {}).setdefault(c["value"], []).append(c["source_index"])
    agreements = []
    differences = []
    for key, values in sorted(by_key.items()):
        if len(values) == 1:
            val, idxs = next(iter(values.items()))
            if len(set(idxs)) >= 2:
                agreements.append({"key": key, "value": val, "source_indexes": sorted(set(idxs))})
        else:
            differences.append(
                {"key": key, "values": [{"value": v, "source_indexes": sorted(set(i))} for v, i in sorted(values.items())]}
            )
    contradictions = find_contradictions(claims)
    winner = None
    if len(agreements) and not contradictions:
        winner = None
    return {"agreements": agreements, "differences": differences, "contradictions": contradictions, "winner": winner}


def detect_contradictions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return find_contradictions(claims)


def selected_headers(headers: dict[str, str]) -> dict[str, str]:
    keep = (
        "content-type",
        "last-modified",
        "etag",
        "cache-control",
        "expires",
        "age",
        "date",
        "server",
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "access-control-allow-origin",
        "location",
    )
    return {k: headers[k] for k in keep if k in headers}


def check_headers(headers: dict[str, str]) -> dict[str, Any]:
    h = {k.lower(): v for k, v in headers.items()}
    present = {
        "strict-transport-security": "strict-transport-security" in h,
        "content-security-policy": "content-security-policy" in h,
        "x-content-type-options": h.get("x-content-type-options", "").lower() == "nosniff",
        "referrer-policy": "referrer-policy" in h,
        "permissions-policy": "permissions-policy" in h or "feature-policy" in h,
        "x-frame-options": "x-frame-options" in h,
        "content-security-policy-frame": "frame-ancestors" in h.get("content-security-policy", "").lower(),
    }
    missing = [k for k, ok in present.items() if not ok]
    return {"present": present, "missing": missing, "headers": selected_headers(h)}


def check_cors(headers: dict[str, str], *, origin: str = "https://example.com") -> dict[str, Any]:
    h = {k.lower(): v for k, v in headers.items()}
    aco = h.get("access-control-allow-origin", "")
    acc = h.get("access-control-allow-credentials", "").lower() == "true"
    wildcard = aco.strip() == "*"
    unsafe = wildcard and acc
    return {
        "probe_origin": origin,
        "allow_origin": aco,
        "allow_credentials": acc,
        "wildcard": wildcard,
        "credential_wildcard_conflict": unsafe,
        "allow_methods": h.get("access-control-allow-methods"),
        "allow_headers": h.get("access-control-allow-headers"),
    }


def check_tls(url: str) -> dict[str, Any]:
    try:
        scheme, host, _path, port, _raw = parse_public_http_url(url)
    except SsrfError as e:
        return {"ok": False, "error": str(e)}
    if scheme != "https":
        return {"ok": False, "tls_available": False, "error": "not_https"}
    try:
        ips = resolve_public(host)
    except SsrfError as e:
        return {"ok": False, "error": str(e)}
    ctx = ssl.create_default_context()
    try:
        sock = socket.create_connection((ips[0], port), timeout=5.0)
        try:
            ssock = ctx.wrap_socket(sock, server_hostname=host)
            cert = ssock.getpeercert()
            proto = ssock.version()
        finally:
            sock.close()
    except Exception as e:
        return {"ok": False, "tls_available": False, "error": type(e).__name__}
    subj = dict(x[0] for x in (cert.get("subject") or ()) if x)
    iss = dict(x[0] for x in (cert.get("issuer") or ()) if x)
    not_after = cert.get("notAfter")
    san = []
    for typ, val in cert.get("subjectAltName") or []:
        if typ == "DNS":
            san.append(val)
    host_match = host in san or subj.get("commonName") == host or any(host.endswith(s[2:]) for s in san if s.startswith("*."))
    return {
        "ok": True,
        "tls_available": True,
        "protocol": proto,
        "subject": subj,
        "issuer": iss,
        "not_after": not_after,
        "san": san[:20],
        "hostname_match": bool(host_match),
        "resolved_ip_public": True,
    }


def check_robots(url: str, fetch_fn: Callable | None = None) -> dict[str, Any]:
    ru = robots_url_for(url)
    fr = fetch_public_url(ru, check_robots=False, fetch_fn=fetch_fn)
    text = (fr.body or b"").decode("utf-8", "replace") if fr.http_status == 200 else None
    return {
        "robots_url": ru,
        "http_status": fr.http_status,
        "allowed": allowed_by_robots(text, url),
        "fetched_at": fr.fetched_at,
        "sha256": fr.content_sha256,
        "error": fr.error,
    }


def check_sitemap(url: str, fetch_fn: Callable | None = None) -> dict[str, Any]:
    p = urlparse(url)
    su = urljoin(f"{p.scheme}://{p.netloc}", "/sitemap.xml")
    fr = fetch_public_url(su, check_robots=False, fetch_fn=fetch_fn)
    body = (fr.body or b"").decode("utf-8", "replace")
    localhost = "localhost" in body.lower() or "127.0.0.1" in body
    return {
        "sitemap_url": su,
        "http_status": fr.http_status,
        "sha256": fr.content_sha256,
        "localhost_leak": localhost,
        "error": fr.error,
    }


def _load_jsonish(body: bytes) -> tuple[Any | None, str | None]:
    text = body.decode("utf-8", "replace").lstrip("\ufeff")
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        return None, "openapi_not_json"


def parse_openapi(body: bytes) -> tuple[dict[str, Any] | None, str | None]:
    data, err = _load_jsonish(body)
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, "openapi_not_object"
    return data, None


def inspect_json_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"ok": False, "error": "schema_not_object"}
    return {
        "ok": True,
        "type": schema.get("type"),
        "required": schema.get("required") if isinstance(schema.get("required"), list) else [],
        "properties": list((schema.get("properties") or {}).keys()) if isinstance(schema.get("properties"), dict) else [],
        "additionalProperties": schema.get("additionalProperties"),
    }


def openapi_audit(spec: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    servers = spec.get("servers") or []
    localhost = False
    for s in servers if isinstance(servers, list) else []:
        u = str((s or {}).get("url") or "").lower()
        if "localhost" in u or "127.0.0.1" in u:
            localhost = True
            issues.append("localhost_server")
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
    ops = 0
    missing_desc = 0
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method not in {"get", "put", "post", "delete", "patch", "options", "head", "trace"}:
                continue
            ops += 1
            if isinstance(op, dict) and not op.get("description") and not op.get("summary"):
                missing_desc += 1
    if not spec.get("openapi") and not spec.get("swagger"):
        issues.append("missing_openapi_version")
    if not paths:
        issues.append("no_paths")
    return {
        "openapi": spec.get("openapi") or spec.get("swagger"),
        "title": (spec.get("info") or {}).get("title") if isinstance(spec.get("info"), dict) else None,
        "servers": servers,
        "operation_count": ops,
        "missing_descriptions": missing_desc,
        "has_security": bool(spec.get("security") or (spec.get("components") or {}).get("securitySchemes")),
        "localhost_urls": localhost,
        "issues": issues,
    }


def diff_openapi(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    def ops(spec: dict) -> dict[tuple[str, str], dict]:
        out = {}
        paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if method in {"get", "put", "post", "delete", "patch", "options", "head"} and isinstance(op, dict):
                    out[(path, method)] = op
        return out

    a, b = ops(old), ops(new)
    removed = [{"path": p, "method": m} for (p, m) in a if (p, m) not in b]
    added = [{"path": p, "method": m} for (p, m) in b if (p, m) not in a]
    required_changes = []
    type_changes = []
    security_changes = []
    response_changes = []
    for key in set(a) & set(b):
        oa, ob = a[key], b[key]
        ra = ((oa.get("requestBody") or {}).get("content") or {})
        rb = ((ob.get("requestBody") or {}).get("content") or {})
        if ra != rb:
            type_changes.append({"path": key[0], "method": key[1], "kind": "requestBody"})
        if (oa.get("security") or []) != (ob.get("security") or []):
            security_changes.append({"path": key[0], "method": key[1]})
        if set((oa.get("responses") or {})) - set((ob.get("responses") or {})):
            response_changes.append({"path": key[0], "method": key[1]})
        pa = ((oa.get("parameters") or []))
        pb = ((ob.get("parameters") or []))

        def reqset(params):
            return {str(p.get("name")) for p in params if isinstance(p, dict) and p.get("required")}

        if reqset(pb) - reqset(pa):
            required_changes.append({"path": key[0], "method": key[1], "added_required": sorted(reqset(pb) - reqset(pa))})
    return {
        "removed_endpoints": removed,
        "added_endpoints": added,
        "required_field_changes": required_changes,
        "type_changes": type_changes,
        "security_changes": security_changes,
        "response_changes": response_changes,
        "breaking": bool(removed or required_changes or type_changes or security_changes or response_changes),
    }


def observed_shape(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "truncated"
    if isinstance(obj, dict):
        return {str(k): observed_shape(v, depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        return [observed_shape(obj[0], depth + 1)] if obj else []
    if obj is None:
        return "null"
    return type(obj).__name__


def mcp_rpc(url: str, method: str, params: dict | None = None, fetch_fn: Callable | None = None) -> dict[str, Any]:
    import http.client

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    try:
        scheme, host, path, port, _ = parse_public_http_url(url)
        ips = resolve_public(host)
    except SsrfError as e:
        return {"ok": False, "error": str(e)}
    ctx = ssl.create_default_context()
    from products.fresh_web_evidence.fetch import PinnedHTTPSConnection

    try:
        if scheme == "https":
            conn: http.client.HTTPConnection = PinnedHTTPSConnection(ips[0], port, 8.0, ctx, host)
        else:
            conn = http.client.HTTPConnection(ips[0], port=port, timeout=8.0)
        conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Accept", "application/json")
        conn.putheader("Content-Length", str(len(payload)))
        conn.putheader("Connection", "close")
        conn.endheaders(payload)
        resp = conn.getresponse()
        raw = resp.read(262144)
        conn.close()
        try:
            data = json.loads(raw.decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid_json", "http_status": resp.status}
        return {"ok": 200 <= resp.status < 300, "http_status": resp.status, "rpc": data}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}


def mcp_initialize(url: str) -> dict[str, Any]:
    return mcp_rpc(
        url,
        "initialize",
        {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ajr-store", "version": "0.16.1"}},
    )


def mcp_tools_list(url: str) -> dict[str, Any]:
    return mcp_rpc(url, "tools/list", {})


def x402_probe(url: str, fetch_fn: Callable | None = None) -> dict[str, Any]:
    """Unpaid probe only. Never sends PAYMENT-SIGNATURE."""
    fr = fetch_public_url(
        url,
        method="POST",
        check_robots=False,
        extra_headers={"Accept": "application/json", "Content-Type": "application/json"},
        keep_error_body=True,
        fetch_fn=fetch_fn,
    )
    body_txt = (fr.body or b"").decode("utf-8", "replace")
    parsed = None
    try:
        parsed = json.loads(body_txt) if body_txt else None
    except json.JSONDecodeError:
        parsed = None
    accepts = (parsed or {}).get("accepts") if isinstance(parsed, dict) else None
    acc = (accepts or [{}])[0] if isinstance(accepts, list) and accepts else {}
    origin = urlparse(url)
    base = f"{origin.scheme}://{origin.netloc}"
    wk = fetch_public_url(base + "/.well-known/x402", check_robots=False, fetch_fn=fetch_fn)
    oa = fetch_public_url(base + "/openapi.json", check_robots=False, fetch_fn=fetch_fn)
    wk_json = None
    try:
        wk_json = json.loads((wk.body or b"").decode("utf-8", "replace") or "{}") if wk.http_status == 200 else None
    except json.JSONDecodeError:
        wk_json = None
    return {
        "probed_url": url,
        "http_status": fr.http_status,
        "expects_402": fr.http_status == 402,
        "payment_required_header": bool(fr.headers.get("payment-required")),
        "network": acc.get("network"),
        "asset": acc.get("asset"),
        "amount": acc.get("amount"),
        "payTo": acc.get("payTo"),
        "scheme": acc.get("scheme"),
        "x402Version": (parsed or {}).get("x402Version") if isinstance(parsed, dict) else None,
        "well_known_x402": wk_json,
        "openapi_http_status": oa.http_status,
        "spent_payment": False,
        "payment_signature_sent": False,
        "error": fr.error if fr.http_status not in {200, 402} else None,
    }


def build_provenance(fr: FetchResult) -> dict[str, Any]:
    return {
        "url": fr.url,
        "requested_url": fr.requested_url,
        "fetched_at": fr.fetched_at,
        "http_status": fr.http_status,
        "content_sha256": fr.content_sha256,
        "content_type": fr.content_type,
        "truncated": fr.truncated,
        "error": fr.error,
    }


def build_receipt(fr: FetchResult) -> dict[str, Any]:
    # Intentionally omit body.
    return {
        "url": fr.url,
        "requested_url": fr.requested_url,
        "timestamp": fr.fetched_at,
        "http_status": fr.http_status,
        "content_type": fr.content_type,
        "sha256": fr.content_sha256,
        "canonical_url": fr.url,
        "headers": selected_headers(fr.headers or {}),
        "error": fr.error,
        "body_stored": False,
    }


def localhost_warnings(text: str) -> list[str]:
    t = text.lower()
    out = []
    if "localhost" in t or "127.0.0.1" in t:
        out.append("localhost_mention")
    if "0.0.0.0" in t:
        out.append("unspecified_bind")
    return out
