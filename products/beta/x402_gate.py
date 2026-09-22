from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from products.beta.settings import (
    MAINNET_PAYMENT_ENABLED,
    PAID_PRICE_USDC,
    PAID_ROUTE_ENABLED,
    SELLER_RECEIVE_ADDRESS,
    X402_NETWORK,
    X402_PAYMENT_ENABLED,
    X402_USDC_BASE,
    current_base_url,
)

PAID_HTTP_PATHS = {"/v1/json/reliable"}
FACILITATOR_MAINNET = "https://api.cdp.coinbase.com/platform/v2/x402"


def payment_flags_on() -> bool:
    return bool(X402_PAYMENT_ENABLED and PAID_ROUTE_ENABLED)


def atomic_amount() -> str:
    # USDC 6 decimals. 0.003 -> 3000, 0.005 -> 5000
    return str(int(round(float(PAID_PRICE_USDC) * 1_000_000)))


def payment_requirements(resource_path: str) -> dict[str, Any]:
    url = current_base_url().rstrip("/") + resource_path
    return {
        "x402Version": 2,
        "error": "PAYMENT-SIGNATURE header is required",
        "resource": {
            "url": url,
            "description": "Deterministic JSON inspect, safe repair, and optional JSON Schema validation.",
            "mimeType": "application/json",
        },
        "accepts": [
            {
                "scheme": "exact",
                "network": X402_NETWORK,
                "amount": atomic_amount(),
                "asset": X402_USDC_BASE,
                "payTo": SELLER_RECEIVE_ADDRESS or "SELLER_RECEIVE_ADDRESS_UNSET",
                "maxTimeoutSeconds": 60,
                "extra": {"name": "USDC", "version": "2"},
            }
        ],
        "extensions": {},
    }


def encode_payment_required(body: dict[str, Any]) -> str:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def verify_and_settle(payment_signature: str | None) -> dict[str, Any]:
    """Never settles while flags are off. Does not fake a successful mainnet settlement."""
    if not payment_flags_on():
        return {"settlement_status": "skipped_flag_off", "tx_hash": None, "payer": None}
    if not SELLER_RECEIVE_ADDRESS:
        return {"settlement_status": "misconfigured_no_receive_address", "tx_hash": None, "payer": None}
    if not MAINNET_PAYMENT_ENABLED:
        return {"settlement_status": "blocked_mainnet_flag_off", "tx_hash": None, "payer": None}
    if not (payment_signature or "").strip():
        return {"settlement_status": "missing_signature", "tx_hash": None, "payer": None}
    # Real facilitator verify/settle is not invoked until MAINNET_PAYMENT_ENABLED and operator wiring.
    # Refuse to invent a tx hash.
    return {
        "settlement_status": "facilitator_not_wired",
        "tx_hash": None,
        "payer": None,
        "facilitator": FACILITATOR_MAINNET,
        "note": "Do not fake settlement. Wire CDP/PayAI facilitator only after explicit authorization.",
    }


def maybe_payment_response(request: Request, path: str) -> JSONResponse | None:
    if path not in PAID_HTTP_PATHS:
        return None
    if not payment_flags_on():
        return None
    if not SELLER_RECEIVE_ADDRESS:
        return JSONResponse(
            {"error": "payment_misconfigured", "error_class": "seller_receive_address_required"},
            status_code=503,
        )
    sig = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature")
    settled = verify_and_settle(sig)
    if settled.get("settlement_status") == "settled":
        request.state.x402_settlement = settled
        return None
    req = payment_requirements(path)
    return JSONResponse(
        req,
        status_code=402,
        headers={"PAYMENT-REQUIRED": encode_payment_required(req)},
    )
