from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from products.beta import paid_ledger
from products.beta.settings import (
    PAID_PRICE_USDC,
    X402_NETWORK,
    X402_USDC_BASE,
    current_base_url,
)

PAID_HTTP_PATHS = {"/v1/json/reliable"}
FACILITATOR_CDP = "https://api.cdp.coinbase.com/platform/v2/x402"
FACILITATOR_PAYAI = "https://facilitator.payai.network"
FACILITATOR_TESTNET = "https://x402.org/facilitator"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def payment_flags_on() -> bool:
    return _env_flag("X402_PAYMENT_ENABLED") and _env_flag("PAID_ROUTE_ENABLED")


def seller_receive_address() -> str:
    return (os.environ.get("SELLER_RECEIVE_ADDRESS") or "").strip()


def mainnet_enabled() -> bool:
    return _env_flag("MAINNET_PAYMENT_ENABLED")


def allow_mock() -> bool:
    return _env_flag("ALLOW_MOCK_X402") and not mainnet_enabled()


def facilitator_mode() -> str:
    if not payment_flags_on():
        return "off"
    if allow_mock():
        return "mock"
    if mainnet_enabled():
        return "cdp"
    return "blocked"


def atomic_amount() -> str:
    return str(int(round(float(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC) * 1_000_000)))


def bazaar_extensions() -> dict[str, Any]:
    """Opt-in Bazaar metadata. Indexed only after a real CDP settle (not mock)."""
    return {
        "bazaar": {
            "info": {
                "input": {
                    "type": "http",
                    "method": "POST",
                    "bodyType": "json",
                    "queryParams": {},
                    "bodySchema": {
                        "type": "object",
                        "required": ["text"],
                        "properties": {
                            "text": {"type": "string", "description": "Malformed or valid JSON text from an agent"},
                            "schema": {"type": "object", "description": "Optional JSON Schema"},
                        },
                    },
                },
                "output": {
                    "example": {
                        "valid_original": False,
                        "repaired": True,
                        "valid_final": True,
                        "json": {"name": "alice", "age": 30},
                    }
                },
            }
        }
    }


def payment_requirements(resource_path: str = "/v1/json/reliable") -> dict[str, Any]:
    url = current_base_url().rstrip("/") + resource_path
    price = os.environ.get("PAID_PRICE_USDC") or str(PAID_PRICE_USDC)
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
                "network": os.environ.get("X402_NETWORK") or X402_NETWORK,
                "amount": atomic_amount(),
                "asset": os.environ.get("X402_USDC_BASE") or X402_USDC_BASE or BASE_USDC,
                "payTo": seller_receive_address() or "SELLER_RECEIVE_ADDRESS_UNSET",
                "maxTimeoutSeconds": 60,
                "extra": {"name": "USDC", "version": "2"},
            }
        ],
        "extensions": bazaar_extensions(),
        "price_usdc": price,
    }


def encode_payment_required(body: dict[str, Any]) -> str:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decode_payment_signature(header: str | None) -> dict[str, Any] | None:
    if not header or not str(header).strip():
        return None
    s = str(header).strip()
    for candidate in (s,):
        try:
            raw = base64.b64decode(candidate, validate=False)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            pass
        try:
            return json.loads(s)
        except Exception:
            return None
    return None


def payment_hash(payload: dict[str, Any] | None, raw_header: str | None) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() if payload else (raw_header or "").encode()
    return hashlib.sha256(blob).hexdigest()


def extract_payer_nonce(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    auth = inner.get("authorization") if isinstance(inner, dict) else None
    if isinstance(auth, dict):
        payer = auth.get("from") or auth.get("payer")
        nonce = auth.get("nonce")
        return (str(payer) if payer else None, str(nonce) if nonce else None)
    payer = payload.get("payer") or payload.get("from")
    nonce = payload.get("nonce")
    return (str(payer) if payer else None, str(nonce) if nonce else None)


def _402(path: str) -> JSONResponse:
    req = payment_requirements(path)
    return JSONResponse(req, status_code=402, headers={"PAYMENT-REQUIRED": encode_payment_required(req)})


def _facilitator_post(kind: str, payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Live CDP verify/settle. Never called when flags are off or mock mode."""
    if kind not in {"verify", "settle"}:
        return {"ok": False, "error": "bad_kind"}
    key_id = (os.environ.get("CDP_API_KEY_ID") or "").strip()
    if not key_id:
        return {"ok": False, "error": "cdp_api_key_missing", "is_real": False}
    url = FACILITATOR_CDP.rstrip("/") + f"/{kind}"
    body = json.dumps(
        {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": requirements.get("accepts", [{}])[0]}
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "agent-json-reliability-x402"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        return {"ok": True, "data": data, "is_real": True}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else str(e)
        return {"ok": False, "error": f"http_{e.code}", "body": raw[:500], "is_real": False}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "is_real": False}


def verify_payment(payload: dict[str, Any] | None, raw_header: str | None) -> dict[str, Any]:
    mode = facilitator_mode()
    if mode == "off":
        return {"verify_status": "skipped_flag_off", "is_real": False}
    if mode == "blocked":
        return {"verify_status": "blocked_mainnet_flag_off", "is_real": False}
    if payload is None:
        return {"verify_status": "missing_or_invalid_signature", "is_real": False}
    ph = payment_hash(payload, raw_header)
    payer, nonce = extract_payer_nonce(payload)
    if paid_ledger.seen_payment(ph, nonce):
        return {"verify_status": "replay_rejected", "is_real": False, "payment_hash": ph, "payer": payer, "nonce": nonce}
    if mode == "mock":
        return {
            "verify_status": "mock_valid",
            "is_real": False,
            "payment_hash": ph,
            "payer": payer,
            "nonce": nonce,
            "note": "MOCK_NOT_REAL_SETTLEMENT",
        }
    reqs = payment_requirements()
    out = _facilitator_post("verify", payload, reqs)
    if not out.get("ok"):
        return {"verify_status": "verify_failed", "is_real": False, "detail": out.get("error"), "payment_hash": ph}
    return {
        "verify_status": "verified",
        "is_real": True,
        "payment_hash": ph,
        "payer": payer,
        "nonce": nonce,
        "facilitator": FACILITATOR_CDP,
        "data": out.get("data"),
    }


def settle_payment(verified: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    mode = facilitator_mode()
    if mode == "off":
        return {"settlement_status": "skipped_flag_off", "tx_hash": None, "is_real": False}
    if verified.get("verify_status") == "replay_rejected":
        return {"settlement_status": "replay_rejected", "tx_hash": None, "is_real": False}
    if mode == "mock":
        receipt = {
            "settlement_status": "mock_settled",
            "tx_hash": None,
            "is_real": False,
            "payer": verified.get("payer"),
            "network": os.environ.get("X402_NETWORK") or X402_NETWORK,
            "asset": "USDC",
            "amount": atomic_amount(),
            "price": str(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC),
            "note": "MOCK_NOT_REAL_SETTLEMENT",
            "payment_hash": verified.get("payment_hash"),
            "nonce": verified.get("nonce"),
        }
        return receipt
    if mode != "cdp" or payload is None:
        return {"settlement_status": "blocked_mainnet_flag_off", "tx_hash": None, "is_real": False}
    out = _facilitator_post("settle", payload, payment_requirements())
    if not out.get("ok") or not out.get("is_real"):
        return {"settlement_status": "settle_failed", "tx_hash": None, "is_real": False, "detail": out.get("error")}
    data = out.get("data") or {}
    tx = data.get("transaction") or data.get("txHash") or data.get("transactionHash")
    return {
        "settlement_status": "settled",
        "tx_hash": tx,
        "is_real": True,
        "payer": verified.get("payer"),
        "network": os.environ.get("X402_NETWORK") or X402_NETWORK,
        "asset": "USDC",
        "amount": atomic_amount(),
        "price": str(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC),
        "payment_hash": verified.get("payment_hash"),
        "nonce": verified.get("nonce"),
        "facilitator": FACILITATOR_CDP,
        "data": data,
    }


def encode_payment_response(receipt: dict[str, Any]) -> str:
    slim = {k: receipt.get(k) for k in ("settlement_status", "tx_hash", "is_real", "network", "asset", "amount", "payer")}
    return base64.b64encode(json.dumps(slim, separators=(",", ":")).encode()).decode("ascii")


def maybe_payment_response(request: Request, path: str) -> JSONResponse | None:
    """Verify-before-work. Returns 402/503 or None to proceed. Does not settle."""
    if path not in PAID_HTTP_PATHS:
        return None
    if not payment_flags_on():
        return None
    if not seller_receive_address() and facilitator_mode() != "mock":
        return JSONResponse(
            {"error": "payment_misconfigured", "error_class": "seller_receive_address_required"},
            status_code=503,
        )
    raw = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature")
    payload = decode_payment_signature(raw)
    verified = verify_payment(payload, raw)
    if verified.get("verify_status") in {"verified", "mock_valid"}:
        request.state.x402_verified = verified
        request.state.x402_payload = payload
        return None
    return _402(path)


def verify_and_settle(payment_signature: str | None) -> dict[str, Any]:
    """Compatibility helper. Flags off never settles. Mock never reports settlement_status=settled."""
    payload = decode_payment_signature(payment_signature)
    verified = verify_payment(payload, payment_signature)
    if verified.get("verify_status") in {"skipped_flag_off"}:
        return {"settlement_status": "skipped_flag_off", "tx_hash": None, "payer": None, "is_real": False}
    if verified.get("verify_status") not in {"verified", "mock_valid"}:
        return {
            "settlement_status": verified.get("verify_status"),
            "tx_hash": None,
            "payer": verified.get("payer"),
            "is_real": False,
        }
    return settle_payment(verified, payload)
