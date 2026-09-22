"""Unknown-external acquisition counters. Listings and crawlers are not users."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from products.beta.settings import TOOL_PATHS
from products.beta.store import _conn

EXCLUDE_KINDS = {
    "INTERNAL_TEST",
    "INTERNAL_EXTERNAL_PATH_TEST",
    "KNOWN_SELF_TEST",
    "LOCALHOST",
    "LIKELY_CRAWLER",
    "SECURITY_SCAN",
    "RANDOM_PROBE",
    "SYNTHETIC_EXTERNAL_BUYER",
    "SYNTHETIC_BUYER",
    "HEALTH_MONITOR",
    "HEALTH_CHECK",
}
FREE_PATHS = {"/v1/json/inspect", "/v1/json/validate", "/v1/json/repair", "/mcp"}
PAID_PATH = "/v1/json/reliable"


def _rows() -> list[dict[str, Any]]:
    try:
        c = _conn()
        out = [dict(r) for r in c.execute("SELECT * FROM events").fetchall()]
        c.close()
        return out
    except Exception:
        return []


def _unknown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if (r.get("traffic_kind") or "") == "REAL_EXTERNAL_UNKNOWN"]


def acquisition_metrics() -> dict[str, Any]:
    unk = _unknown(_rows())
    free = [
        r
        for r in unk
        if (r.get("endpoint") or "") in FREE_PATHS and int(r.get("http_status") or 0) in range(200, 400)
    ]
    c402 = [r for r in unk if (r.get("endpoint") or "") == PAID_PATH and int(r.get("http_status") or 0) == 402]
    attempts = [
        r
        for r in unk
        if (r.get("endpoint") or "") == PAID_PATH and (r.get("probe_class") or "") == "payment_attempt"
    ]
    sources: dict[str, int] = defaultdict(int)
    for r in unk:
        ep = r.get("endpoint") or ""
        if ep in TOOL_PATHS or ep == "/mcp" or int(r.get("http_status") or 0) == 402:
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

    return {
        "UNKNOWN_EXTERNAL_FREE_CALLS": len(free),
        "UNKNOWN_EXTERNAL_402_CALLS": len(c402),
        "PAYMENT_ATTEMPTS": len(attempts),
        "SOURCE_DISTRIBUTION": dict(sources),
        "TOP_EXTERNAL_SOURCE": top,
        "LAST_EXTERNAL_CALL_AT": last_ts(unk),
        "LAST_PAYMENT_ATTEMPT_AT": last_ts(attempts),
        "LAST_UNKNOWN_402_AT": last_ts(c402),
    }
