from __future__ import annotations

from products.beta.paid_ledger import paid_metrics
from products.beta.settings import current_base_url, is_https_public
from products.beta.product_registry import active_paid_products
from products.beta.x402_gate import payment_flags_on, payment_requirements
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
    paid = payment_flags_on()
    reqs = payment_requirements("/v1/json/reliable") if paid else None
    ts = []
    for t in _json_tools():
        rec = dict(t)
        rec["resource"] = base + t["path"]
        rec["deterministic"] = True
        rec["llm_required"] = False
        is_paid = paid and t.get("path") == "/v1/json/reliable"
        rec["free_beta"] = not is_paid
        rec["payment_required"] = is_paid
        if is_paid:
            rec["notice"] = "x402 exact payment required: 0.003 USDC on Base (eip155:8453). MCP and inspect/validate/repair remain free."
            rec["x402"] = {
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": "USDC",
                "amount_atomic": "3000",
                "price_usdc": "0.003",
                "facilitator": "PayAI",
                "transferMethod": "eip3009",
            }
            if reqs:
                rec["x402"]["payTo_configured"] = bool((reqs.get("accepts") or [{}])[0].get("payTo"))
        else:
            rec["notice"] = "FREE. NO PAYMENT REQUIRED."
        if t["tool_name"] == "reliable_json":
            rec["capability"] = "json_reliable"
            rec["description"] = PRIMARY_DESCRIPTION
        ts.append(rec)
    return {
        "version": "0.16.1",
        "name": "Agent JSON Reliability",
        "free_beta": not paid,
        "FREE_BETA": not paid,
        "payment_required": paid,
        "PAYMENT_REQUIRED": paid,
        "deterministic": True,
        "llm_required": False,
        "primary_capability": "json_reliable",
        "primary_endpoint": "/v1/json/reliable",
        "primary_product": "AGENT_JSON_RELIABILITY",
        "hero": PRIMARY_DESCRIPTION,
        "base_url": base,
        "public_https": is_https_public(base),
        "services": ts,
        "x402_payments": paid,
        "X402_PAYMENT_ENABLED": paid,
        "PAID_ROUTE_ENABLED": paid,
        "PAID_ENDPOINT": "/v1/json/reliable",
        "PRICE_ATOMIC": 3000,
        "PRICE_USDC": 0.003,
        "NETWORK": "eip155:8453",
        "ASSET": "USDC",
        "FACILITATOR": "PayAI",
        "store_products": [
            {
                "id": p["id"],
                "name": p["name"],
                "path": p["path"],
                "price_usdc": p["price_usdc"],
                "price_atomic": p["price_atomic"],
                "category": p["category"],
                "description": p["description"],
                "payment_required": True,
            }
            for p in active_paid_products()
        ],
        "BAZAAR_DISCOVERY_READY": paid,
        "CIRCLE_DISCOVERY_READY": paid,
        "BAZAAR_ELIGIBLE": real_paid >= 1,
        "CIRCLE_DISCOVERY_ELIGIBLE": real_paid >= 1,
        "REAL_PAID_CALLS": real_paid,
        "limits": {
            "MAX_REQUEST_BODY_BYTES": 262144,
            "MAX_JSON_DEPTH": 64,
            "MAX_REQUESTS_PER_MINUTE_PER_SESSION": 30,
            "MAX_REAL_PAID_CALLS": 10,
            "MAX_DISTINCT_PAID_BUYERS": 5,
        },
        "examples": [
            {
                "input": {"text": "{'a': 1}", "schema": {"type": "object"}},
                "path": "/v1/json/reliable",
            }
        ],
    }
