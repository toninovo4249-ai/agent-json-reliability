"""Unknown-external acquisition counters. Directory/index probes are not buyers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from products.beta.identity import traffic_class
from products.beta.settings import TOOL_PATHS
from products.beta.store import _conn

EXCLUDE_KINDS = {
    "INTERNAL_TEST",
    "INTERNAL_EXTERNAL_PATH_TEST",
    "KNOWN_SELF_TEST",
    "LOCALHOST",
    "LIKELY_CRAWLER",
    "DIRECTORY_PROBE",
    "SECURITY_SCAN",
    "RANDOM_PROBE",
    "SYNTHETIC_EXTERNAL_BUYER",
    "SYNTHETIC_BUYER",
    "SYNTHETIC",
    "HEALTH_MONITOR",
    "HEALTH_CHECK",
}
FREE_PATHS = {
    "/v1/json/inspect",
    "/v1/json/validate",
    "/v1/json/repair",
    "/mcp",
    "/v1/catalog",
    "/v1/catalog/select",
    "/products",
    "/.well-known/agent-products.json",
    "/skill.md",
}
PAID_PATH = "/v1/json/reliable"
SWEEP_DISTINCT_PAID_402 = 6
SWEEP_TOTAL_PAID_402 = 8


def _paid_paths() -> set[str]:
    try:
        from products.beta.product_registry import PRODUCTS

        return {p["path"] for p in PRODUCTS} or {PAID_PATH}
    except Exception:
        return {PAID_PATH}


def _rows() -> list[dict[str, Any]]:
    try:
        c = _conn()
        out = [dict(r) for r in c.execute("SELECT * FROM events").fetchall()]
        c.close()
        return out
    except Exception:
        return []


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def directory_sweep_hashes(rows: list[dict[str, Any]], paid: set[str]) -> set[str]:
    """Generic urllib/indexer clients that fan-out 402s across the catalog."""
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if int(r.get("http_status") or 0) != 402:
            continue
        if (r.get("endpoint") or "") not in paid:
            continue
        h = r.get("anonymous_client_hash") or ""
        if h:
            by_hash[h].append(r)
    out: set[str] = set()
    for h, items in by_hash.items():
        eps = {i.get("endpoint") for i in items}
        if len(eps) >= SWEEP_DISTINCT_PAID_402 or len(items) >= SWEEP_TOTAL_PAID_402:
            out.add(h)
    return out


def classify_event(row: dict[str, Any], sweep: set[str]) -> str:
    kind = row.get("traffic_kind") or ""
    cls = traffic_class(kind)
    h = row.get("anonymous_client_hash") or ""
    if h and h in sweep:
        return "DIRECTORY_PROBE"
    src = str(row.get("self_reported_source") or "").strip().lower()
    if src in {"x402scan", "402index", "indexnow", "payai", "circle", "bazaar"}:
        return "DIRECTORY_PROBE"
    return cls


def _unknown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paid = _paid_paths()
    sweep = directory_sweep_hashes(rows, paid)
    return [r for r in rows if classify_event(r, sweep) == "REAL_EXTERNAL_AGENT"]


def acquisition_metrics(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = _rows() if rows is None else rows
    paid = _paid_paths()
    sweep = directory_sweep_hashes(rows, paid)
    real = [r for r in rows if classify_event(r, sweep) == "REAL_EXTERNAL_AGENT"]
    directory = [r for r in rows if classify_event(r, sweep) == "DIRECTORY_PROBE"]
    synthetic = [r for r in rows if classify_event(r, sweep) == "SYNTHETIC"]
    search = [r for r in rows if classify_event(r, sweep) == "SEARCH_CRAWLER"]
    mcp_reg = [r for r in rows if classify_event(r, sweep) == "MCP_REGISTRY_PROBE"]

    def free_ok(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            r
            for r in group
            if (r.get("endpoint") or "") in FREE_PATHS and int(r.get("http_status") or 0) in range(200, 400)
        ]

    def calls_402(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in group if (r.get("endpoint") or "") in paid and int(r.get("http_status") or 0) == 402]

    catalog_views = [
        r
        for r in real
        if (r.get("endpoint") or "") in {"/v1/catalog", "/products", "/.well-known/agent-products.json"}
        and int(r.get("http_status") or 0) == 200
    ]
    catalog_sel = [
        r
        for r in real
        if (r.get("endpoint") or "") == "/v1/catalog/select" and int(r.get("http_status") or 0) == 200
    ]
    skill_views = [r for r in real if (r.get("endpoint") or "") == "/skill.md" and int(r.get("http_status") or 0) == 200]
    mcp_disc = [r for r in real if (r.get("probe_class") or "") == "mcp_discovery"]
    attr = defaultdict(int)
    for r in real:
        src = str(r.get("self_reported_source") or "unknown").lower()
        if src in {"circle", "x402scan", "mcp_registry", "mcp-registry", "glama", "402index", "payai"}:
            attr[src.replace("-", "_")] += 1
        else:
            attr["unknown"] += 1
    c402 = calls_402(real)
    d402 = calls_402(directory)
    s402 = calls_402(synthetic)
    attempts = [
        r
        for r in real
        if (r.get("endpoint") or "") in paid and (r.get("probe_class") or "") == "payment_attempt"
    ]
    by_402: dict[str, int] = defaultdict(int)
    by_att: dict[str, int] = defaultdict(int)
    for r in c402:
        by_402[r.get("endpoint") or ""] += 1
    for r in attempts:
        by_att[r.get("endpoint") or ""] += 1
    sources: dict[str, int] = defaultdict(int)
    for r in real:
        ep = r.get("endpoint") or ""
        if ep in TOOL_PATHS or ep in FREE_PATHS or ep in paid or int(r.get("http_status") or 0) == 402:
            sources[r.get("self_reported_source") or "unset"] += 1

    def last_ts(items: list[dict[str, Any]]) -> str | None:
        stamps = [r.get("timestamp_utc") for r in items if r.get("timestamp_utc")]
        return max(stamps) if stamps else None

    top = None
    if sources:
        ranked = sorted(sources.items(), key=lambda kv: (-kv[1], kv[0] == "unset"))
        top = ranked[0][0]
        if top == "unset" and len(ranked) > 1:
            top = ranked[1][0]

    real_402_n = len(c402)
    return {
        "UNKNOWN_EXTERNAL_FREE_CALLS": len(free_ok(real)),
        "UNKNOWN_EXTERNAL_402_CALLS": real_402_n,
        "TOTAL_UNKNOWN_EXTERNAL_402_CALLS": real_402_n,
        "REAL_EXTERNAL_FREE_CALLS": len(free_ok(real)),
        "REAL_EXTERNAL_402_CALLS": real_402_n,
        "REAL_EXTERNAL_AGENT_402_CALLS": real_402_n,
        "DIRECTORY_402_PROBES": len(d402),
        "SYNTHETIC_402_PROBES": len(s402),
        "SEARCH_CRAWLER_402_PROBES": len(calls_402(search)),
        "MCP_REGISTRY_402_PROBES": len(calls_402(mcp_reg)),
        "PAYMENT_ATTEMPTS": len(attempts),
        "CATALOG_EXTERNAL_VIEWS": len(catalog_views),
        "CATALOG_VIEWS": len(catalog_views),
        "CATALOG_EXTERNAL_SELECTIONS": len(catalog_sel),
        "SELECTOR_CALLS": len(catalog_sel),
        "SKILL_MD_VIEWS": len(skill_views),
        "MCP_DISCOVERY_TOOL_CALLS": len(mcp_disc),
        "ATTRIBUTION": dict(attr),
        "UNKNOWN_EXTERNAL_402_BY_ENDPOINT": dict(by_402),
        "REAL_EXTERNAL_402_BY_ENDPOINT": dict(by_402),
        "PAYMENT_ATTEMPTS_BY_ENDPOINT": dict(by_att),
        "SOURCE_DISTRIBUTION": dict(sources),
        "TOP_EXTERNAL_SOURCE": top,
        "LAST_EXTERNAL_CALL_AT": last_ts(real),
        "LAST_PAYMENT_ATTEMPT_AT": last_ts(attempts),
        "LAST_UNKNOWN_402_AT": last_ts(c402),
        "DIRECTORY_SWEEP_CLIENTS": len(sweep),
    }
