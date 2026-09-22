"""Product composers. Local JSON work or SSRF-safe fetch after payment verify."""
from __future__ import annotations

from typing import Any, Callable

from products.agent_json_reliability.validate import validate_json
from products.agent_utility import primitives as P
from products.fresh_web_evidence.extract import extract_claims, facts_from_claims
from products.fresh_web_evidence.pack import build_pack, normalize_urls
from products.fresh_web_evidence.ssrf import SsrfError

FetchFn = Callable[..., Any]


def _one_url(body: dict[str, Any], key: str = "url") -> str:
    u = body.get(key) or (body.get("urls") or [None])[0]
    if not u or not str(u).strip():
        raise ValueError("url_required")
    return str(u).strip()


def _urls(body: dict[str, Any], min_n: int = 1) -> list[str]:
    urls = normalize_urls(body)
    if len(urls) < min_n:
        raise ValueError("too_few_urls")
    return urls


def json_contract_check(body: dict[str, Any]) -> dict[str, Any]:
    doc = body.get("json")
    if "json" not in body and "document" in body:
        doc = body.get("document")
    if "json" not in body and "instance" in body:
        doc = body.get("instance")
    schema = body.get("schema")
    if schema is not None and not isinstance(schema, dict):
        raise ValueError("schema_must_be_object")
    if doc is None:
        raise ValueError("json_or_document_required")
    core = validate_json(doc, schema)
    missing: list[str] = []
    additional: list[str] = []
    type_mismatch: list[str] = []
    if isinstance(schema, dict) and isinstance(doc, dict):
        req = schema.get("required") if isinstance(schema.get("required"), list) else []
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        missing = [str(k) for k in req if k not in doc]
        if props:
            additional = [k for k in doc.keys() if k not in props]
        for k, spec in props.items():
            if k in doc and isinstance(spec, dict) and spec.get("type"):
                got = type(doc[k]).__name__
                want = spec.get("type")
                mapping = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "dict": "object", "list": "array", "NoneType": "null"}
                if mapping.get(got) != want and not (want == "number" and got in {"int", "float"}):
                    type_mismatch.append(k)
    return {
        **core,
        "valid": bool(core.get("ok")),
        "missing_keys": missing,
        "additional_keys": additional,
        "type_mismatches": type_mismatch,
        "deterministic": True,
        "llm_used": False,
    }


def _walk_diff(before: Any, after: Any, path: str, acc: dict[str, list]) -> None:
    if type(before) is not type(after) and not (before is None or after is None):
        acc["changed_types"].append({"path": path, "before": type(before).__name__, "after": type(after).__name__})
        acc["changed_values"].append({"path": path})
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for k in before.keys() - after.keys():
            acc["removed_keys"].append(f"{path}/{k}" if path else k)
        for k in after.keys() - before.keys():
            acc["added_keys"].append(f"{path}/{k}" if path else k)
        for k in before.keys() & after.keys():
            _walk_diff(before[k], after[k], f"{path}/{k}" if path else str(k), acc)
        return
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            acc["changed_values"].append({"path": path, "before_len": len(before), "after_len": len(after)})
        for i, (a, b) in enumerate(zip(before, after)):
            _walk_diff(a, b, f"{path}/{i}", acc)
        return
    if before != after:
        acc["changed_values"].append({"path": path, "before": before, "after": after})


def json_diff(body: dict[str, Any]) -> dict[str, Any]:
    if "before" not in body or "after" not in body:
        raise ValueError("before_and_after_required")
    acc = {"added_keys": [], "removed_keys": [], "changed_types": [], "changed_values": []}
    _walk_diff(body.get("before"), body.get("after"), "", acc)
    compatible = not acc["removed_keys"] and not acc["changed_types"]
    return {**acc, "structural_compatibility": compatible, "llm_used": False}


def _fetch(url: str, fetch_fn: FetchFn | None = None, **kw):
    return P.fetch_public_url(url, fetch_fn=fetch_fn, **kw)


def web_extract(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn)
    text = P.extract_html_text(fr)
    meta = P.extract_metadata(fr)
    return {
        "title": text["title"] or meta["title"],
        "headings": text["headings"],
        "main_text": text["text"],
        "metadata": meta,
        "structured_sections": text["sections"],
        "provenance": P.build_provenance(fr),
        "llm_used": False,
    }


def web_markdown(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn)
    return {
        "markdown": P.html_to_markdown(fr),
        "source_url": fr.url,
        "timestamp": fr.fetched_at,
        "sha256": fr.content_sha256,
        "error": fr.error,
        "llm_used": False,
    }


def web_tables(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn)
    return {"tables": P.extract_tables(fr), "provenance": P.build_provenance(fr), "llm_used": False}


def web_metadata(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn)
    meta = P.extract_metadata(fr)
    return {**meta, "provenance": P.build_provenance(fr), "llm_used": False}


def web_link_map(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn)
    return {**P.extract_links(fr), "provenance": P.build_provenance(fr), "llm_used": False}


def evidence_pack(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    return build_pack(body, fetch_fn=fetch_fn)


def evidence_compare(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    urls = _urls(body, min_n=2)
    claims = []
    sources = []
    fn = fetch_fn or (lambda u: P.fetch_public_url(u))
    for i, u in enumerate(urls):
        fr = fn(u) if fetch_fn else P.fetch_public_url(u)
        sources.append(P.build_provenance(fr))
        claims.extend(extract_claims(fr, i))
    cmp = P.compare_sources(claims)
    return {**cmp, "facts": facts_from_claims(claims), "sources": sources, "winner": None, "llm_used": False}


def evidence_contradictions(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    out = evidence_compare(body, fetch_fn=fetch_fn)
    groups = []
    for c in out.get("contradictions") or []:
        groups.append(
            {
                "claim": c.get("claim"),
                "values": c.get("values"),
                "winner": None,
                "sources": [s.get("url") for s in out.get("sources") or []],
                "timestamps": [s.get("fetched_at") for s in out.get("sources") or []],
            }
        )
    return {"contradiction_groups": groups, "winner": None, "llm_used": False}


def evidence_freshness(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn, check_robots=False)
    h = fr.headers or {}
    return {
        "url": fr.url,
        "fetched_at": fr.fetched_at,
        "last_modified": h.get("last-modified"),
        "etag": h.get("etag"),
        "content_hash": fr.content_sha256,
        "cache_headers": {k: h[k] for k in ("cache-control", "expires", "age", "pragma") if k in h},
        "http_status": fr.http_status,
        "freshness_indicators": {
            "has_last_modified": "last-modified" in h,
            "has_etag": "etag" in h,
            "has_cache_control": "cache-control" in h,
        },
        "error": fr.error,
        "llm_used": False,
    }


def evidence_receipt(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn, check_robots=False)
    rec = P.build_receipt(fr)
    rec["llm_used"] = False
    return rec


def url_preflight(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn, check_robots=False, max_redirects=5)
    tls = P.check_tls(url)
    robots = P.check_robots(url, fetch_fn=fetch_fn)
    sitemap = P.check_sitemap(url, fetch_fn=fetch_fn)
    oa = _fetch(urljoin_openapi(url), fetch_fn, check_robots=False)
    oa_spec, oa_err = P.parse_openapi(oa.body or b"") if oa.http_status == 200 else (None, oa.error)
    audit = P.openapi_audit(oa_spec) if oa_spec else {"error": oa_err}
    text = (fr.body or b"").decode("utf-8", "replace")
    return {
        "tls": tls,
        "headers": P.check_headers(fr.headers or {}),
        "redirects": fr.hops,
        "robots": robots,
        "openapi": audit,
        "sitemap": sitemap,
        "localhost_leaks": P.localhost_warnings(text),
        "deployment_warnings": P.localhost_warnings(text),
        "timestamp": fr.fetched_at,
        "provenance": P.build_provenance(fr),
        "llm_used": False,
    }


def urljoin_openapi(url: str) -> str:
    from urllib.parse import urljoin, urlparse

    p = urlparse(url)
    return urljoin(f"{p.scheme}://{p.netloc}", "/openapi.json")


def url_security_headers(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn, check_robots=False)
    return {**P.check_headers(fr.headers or {}), "provenance": P.build_provenance(fr), "llm_used": False}


def url_cors_check(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    origin = str(body.get("origin") or "https://example.com")
    fr = _fetch(
        url,
        fetch_fn,
        method="OPTIONS",
        check_robots=False,
        extra_headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
        keep_error_body=True,
    )
    cors = P.check_cors(fr.headers or {}, origin=origin)
    cors["preflight_status"] = fr.http_status
    cors["provenance"] = P.build_provenance(fr)
    cors["llm_used"] = False
    return cors


def url_tls_check(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    try:
        P.ssrf_guard(url)
    except SsrfError as e:
        raise ValueError(str(e)) from e
    out = P.check_tls(url)
    out["llm_used"] = False
    return out


def url_robots_audit(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    from urllib.parse import urljoin, urlparse

    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    targets = {
        "robots.txt": base + "/robots.txt",
        "llms.txt": base + "/llms.txt",
        "AGENTS.md": base + "/AGENTS.md",
        "sitemap.xml": base + "/sitemap.xml",
        "agent.json": base + "/.well-known/agent.json",
    }
    found = {}
    for name, u in targets.items():
        fr = _fetch(u, fetch_fn, check_robots=False)
        found[name] = {
            "url": u,
            "http_status": fr.http_status,
            "sha256": fr.content_sha256,
            "error": fr.error,
            "present": fr.http_status == 200,
        }
    return {"origin": base, "resources": found, "llm_used": False}


def url_redirect_check(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    fr = _fetch(url, fetch_fn, check_robots=False, max_redirects=5)
    hops = fr.hops or []
    domains = []
    downgrade = False
    prev_https = url.lower().startswith("https://")
    seen = set()
    loop = False
    for h in hops:
        u = h.get("url") or ""
        domains.append(u)
        if u in seen:
            loop = True
        seen.add(u)
        if prev_https and u.lower().startswith("http://"):
            downgrade = True
        prev_https = u.lower().startswith("https://")
    return {
        "hops": hops,
        "status_codes": [h.get("status") for h in hops],
        "domains": domains,
        "protocol_downgrade": downgrade,
        "loops": loop,
        "final_url": fr.url,
        "error": fr.error,
        "llm_used": False,
    }


def _spec_from_body_or_url(body: dict[str, Any], key: str, url_key: str, fetch_fn: FetchFn | None) -> dict[str, Any]:
    if isinstance(body.get(key), dict):
        return body[key]
    u = body.get(url_key) or body.get("url")
    if not u:
        raise ValueError(f"{key}_or_{url_key}_required")
    fr = _fetch(str(u), fetch_fn, check_robots=False)
    spec, err = P.parse_openapi(fr.body or b"")
    if not spec:
        raise ValueError(err or "openapi_parse_failed")
    return spec


def api_openapi_audit(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    spec = _spec_from_body_or_url(body, "spec", "url", fetch_fn)
    audit = P.openapi_audit(spec)
    audit["llm_used"] = False
    return audit


def api_openapi_diff(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    old = body.get("old") or body.get("old_spec")
    new = body.get("new") or body.get("new_spec")
    if not isinstance(old, dict):
        ou = body.get("old_url")
        if not ou:
            raise ValueError("old_spec_or_old_url_required")
        fr = _fetch(str(ou), fetch_fn, check_robots=False)
        old, err = P.parse_openapi(fr.body or b"")
        if not old:
            raise ValueError(err or "old_openapi_parse_failed")
    if not isinstance(new, dict):
        nu = body.get("new_url")
        if not nu:
            raise ValueError("new_spec_or_new_url_required")
        fr = _fetch(str(nu), fetch_fn, check_robots=False)
        new, err = P.parse_openapi(fr.body or b"")
        if not new:
            raise ValueError(err or "new_openapi_parse_failed")
    out = P.diff_openapi(old, new)
    out["llm_used"] = False
    return out


def api_schema_drift(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    live = body.get("endpoint") or body.get("live_url")
    if not live:
        raise ValueError("live_url_required")
    method = str(body.get("method") or "GET").upper()
    if method not in P.SAFE_HTTP_METHODS:
        raise ValueError("unsafe_method")
    spec = body.get("schema") or body.get("openapi")
    if not isinstance(spec, dict):
        su = body.get("openapi_url")
        if su:
            frs = _fetch(str(su), fetch_fn, check_robots=False)
            spec, err = P.parse_openapi(frs.body or b"")
            if not spec:
                raise ValueError(err or "openapi_parse_failed")
        else:
            raise ValueError("schema_or_openapi_required")
    fr = _fetch(str(live), fetch_fn, method=method, check_robots=False)
    try:
        import json as _json

        observed = _json.loads((fr.body or b"").decode("utf-8", "replace")) if fr.http_status == 200 and fr.body else None
        parse_err = None
    except Exception:
        parse_err = "not_json"
        observed = None
    shape = P.observed_shape(observed) if observed is not None else None
    declared = None
    if isinstance(spec.get("properties"), dict) or spec.get("type"):
        declared = P.inspect_json_schema(spec)
    return {
        "live_url": str(live),
        "method": method,
        "http_status": fr.http_status,
        "observed_shape": shape,
        "declared_schema": declared,
        "parse_error": parse_err or fr.error,
        "llm_used": False,
    }


def mcp_preflight(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = _one_url(body)
    try:
        P.ssrf_guard(url)
    except SsrfError as e:
        raise ValueError(str(e)) from e
    init = P.mcp_initialize(url)
    tools = P.mcp_tools_list(url)
    rpc = tools.get("rpc") if isinstance(tools.get("rpc"), dict) else {}
    listed = ((rpc.get("result") or {}).get("tools") if isinstance(rpc.get("result"), dict) else None) or []
    schemas = []
    if isinstance(listed, list):
        for t in listed[:50]:
            if isinstance(t, dict):
                schemas.append({"name": t.get("name"), "has_schema": bool(t.get("inputSchema") or t.get("input_schema"))})
    return {
        "initialize": {"ok": init.get("ok"), "http_status": init.get("http_status"), "error": init.get("error")},
        "tools_list": {"ok": tools.get("ok"), "http_status": tools.get("http_status"), "error": tools.get("error")},
        "tool_count": len(schemas),
        "tool_schemas": schemas,
        "server_info": (init.get("rpc") or {}).get("result") if isinstance(init.get("rpc"), dict) else None,
        "tools_executed": False,
        "llm_used": False,
    }


def x402_preflight(body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    url = body.get("url") or body.get("endpoint")
    if not url:
        raise ValueError("url_required")
    try:
        P.ssrf_guard(str(url))
    except SsrfError as e:
        raise ValueError(str(e)) from e
    out = P.x402_probe(str(url), fetch_fn=fetch_fn)
    out["llm_used"] = False
    out["paid_upstream_used"] = False
    return out


HANDLERS: dict[str, Callable] = {
    "json_contract_check": json_contract_check,
    "json_diff": json_diff,
    "web_extract": web_extract,
    "web_markdown": web_markdown,
    "web_tables": web_tables,
    "web_metadata": web_metadata,
    "web_link_map": web_link_map,
    "evidence_compare": evidence_compare,
    "evidence_contradictions": evidence_contradictions,
    "evidence_freshness": evidence_freshness,
    "evidence_receipt": evidence_receipt,
    "url_preflight": url_preflight,
    "url_security_headers": url_security_headers,
    "url_cors_check": url_cors_check,
    "url_tls_check": url_tls_check,
    "url_robots_audit": url_robots_audit,
    "url_redirect_check": url_redirect_check,
    "api_openapi_audit": api_openapi_audit,
    "api_openapi_diff": api_openapi_diff,
    "api_schema_drift": api_schema_drift,
    "mcp_preflight": mcp_preflight,
    "x402_preflight": x402_preflight,
}


def run_product(product_id: str, body: dict[str, Any], fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    fn = HANDLERS.get(product_id)
    if fn is None:
        raise ValueError("unknown_product")
    try:
        return fn(body, fetch_fn=fetch_fn) if product_id not in {"json_contract_check", "json_diff"} else fn(body)
    except TypeError:
        return fn(body)
