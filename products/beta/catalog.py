from __future__ import annotations

from products.beta.paid_ledger import paid_metrics
from products.beta.settings import current_base_url, is_https_public
from products.gateway.manifest import tools


PRIMARY_DESCRIPTION = (
    "Inspect malformed JSON, safely repair common structural errors without inventing semantic values, "
    "and optionally validate the resulting object against a supplied JSON Schema."
)


def _json_tools():
    return [t for t in tools() if t["product_family"] == "AGENT_JSON_RELIABILITY"]


def public_catalog() -> dict:
    base = current_base_url()
    real_paid = int(paid_metrics().get("REAL_PAID_CALLS") or 0)
    ts = []
    for t in _json_tools():
        rec = dict(t)
        rec["resource"] = base + t["path"]
        rec["free_beta"] = True
        rec["payment_required"] = False
        rec["deterministic"] = True
        rec["llm_required"] = False
        rec["notice"] = "FREE BETA. NO PAYMENT REQUIRED. Not a paid x402 settlement endpoint."
        if t["tool_name"] == "reliable_json":
            rec["capability"] = "json_reliable"
            rec["description"] = PRIMARY_DESCRIPTION
        ts.append(rec)
    return {
        "version": "0.16.1",
        "name": "Agent JSON Reliability",
        "free_beta": True,
        "FREE_BETA": True,
        "payment_required": False,
        "PAYMENT_REQUIRED": False,
        "deterministic": True,
        "llm_required": False,
        "primary_capability": "json_reliable",
        "primary_endpoint": "/v1/json/reliable",
        "primary_product": "AGENT_JSON_RELIABILITY",
        "hero": PRIMARY_DESCRIPTION,
        "base_url": base,
        "public_https": is_https_public(base),
        "services": ts,
        "x402_payments": False,
        "X402_PAYMENT_ENABLED": False,
        "PAID_ROUTE_ENABLED": False,
        "BAZAAR_ELIGIBLE": real_paid >= 1,
        "CIRCLE_DISCOVERY_ELIGIBLE": real_paid >= 1,
        "REAL_PAID_CALLS": real_paid,
        "limits": {
            "MAX_REQUEST_BODY_BYTES": 262144,
            "MAX_JSON_DEPTH": 64,
            "MAX_REQUESTS_PER_MINUTE_PER_SESSION": 30,
        },
        "examples": [
            {
                "input": {"text": "{'a': 1}", "schema": {"type": "object"}},
                "path": "/v1/json/reliable",
            }
        ],
    }
