from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from products.beta import paid_ledger
from products.beta.cdp_jwt import SETTLE_PATH, SUPPORTED_PATH, VERIFY_PATH, auth_headers, cdp_auth_configured
from products.beta.settings import (
    PAID_PRICE_USDC,
    X402_NETWORK,
    X402_USDC_BASE,
    current_base_url,
)

PAID_HTTP_PATHS = {"/v1/json/reliable"}
FACILITATOR_CDP = "https://api.cdp.coinbase.com/platform/v2/x402"
FACILITATOR_PAYAI = "https://facilitator.payai.network"
FACILITATOR_DEXTER = "https://x402.dexter.cash"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
REQUIRED_NETWORK = "eip155:8453"
REQUIRED_ATOMIC = "3000"
MAX_PAID_REQUESTS_BEFORE_REVIEW = 10
MAX_DISTINCT_PAID_BUYERS_BEFORE_REVIEW = 5


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def payment_flags_on() -> bool:
    return _env_flag("X402_PAYMENT_ENABLED") and _env_flag("PAID_ROUTE_ENABLED")


def seller_receive_address() -> str:
    return (os.environ.get("SELLER_RECEIVE_ADDRESS") or "").strip()


def valid_seller_receive_address(addr: str | None = None) -> bool:
    a = (addr if addr is not None else seller_receive_address()).strip()
    return bool(EVM_ADDRESS_RE.fullmatch(a))


def mainnet_enabled() -> bool:
    return _env_flag("MAINNET_PAYMENT_ENABLED")


def allow_mock() -> bool:
    return _env_flag("ALLOW_MOCK_X402") and not mainnet_enabled()


def first_paid_buyer_mode() -> bool:
    v = (os.environ.get("FIRST_PAID_BUYER_MODE") or "true").strip().lower()
    return v in {"1", "true", "yes", "on"}


def selected_facilitator() -> str:
    """Production facilitator. auto = PayAI (no CDP signup) unless CDP JWT creds exist."""
    choice = (os.environ.get("X402_FACILITATOR") or "auto").strip().lower()
    if choice in {"payai", "dexter", "cdp"}:
        return choice
    if cdp_auth_configured():
        return "cdp"
    return "payai"


def facilitator_base_url() -> str:
    name = selected_facilitator()
    if name == "dexter":
        return FACILITATOR_DEXTER
    if name == "cdp":
        return FACILITATOR_CDP
    return FACILITATOR_PAYAI


def facilitator_mode() -> str:
    if not payment_flags_on():
        return "off"
    if allow_mock():
        return "mock"
    if mainnet_enabled():
        return selected_facilitator()
    return "blocked"


def atomic_amount() -> str:
    raw = (os.environ.get("X402_PRICE_ATOMIC") or "").strip()
    if raw:
        try:
            return str(int(raw))
        except ValueError:
            return "INVALID"
    return str(int(round(float(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC) * 1_000_000)))


def configured_network() -> str:
    return (os.environ.get("X402_NETWORK") or X402_NETWORK or REQUIRED_NETWORK).strip()


def configured_asset() -> str:
    return (os.environ.get("X402_USDC_BASE") or X402_USDC_BASE or BASE_USDC).strip()


def paid_route_blockers() -> list[str]:
    """Fail-closed reasons for the paid route. Empty means config is internally consistent."""
    errs: list[str] = []
    if not valid_seller_receive_address():
        errs.append("seller_receive_address_invalid_or_missing")
    if configured_network() != REQUIRED_NETWORK:
        errs.append("invalid_network")
    if configured_asset().lower() != BASE_USDC.lower():
        errs.append("invalid_asset")
    if atomic_amount() != REQUIRED_ATOMIC:
        errs.append("invalid_price")
    if first_paid_buyer_mode():
        m = paid_ledger.paid_metrics()
        if int(m.get("REAL_PAID_CALLS") or 0) >= MAX_PAID_REQUESTS_BEFORE_REVIEW:
            errs.append("first_paid_buyer_max_requests")
        if int(m.get("DISTINCT_REAL_PAID_BUYERS") or 0) >= MAX_DISTINCT_PAID_BUYERS_BEFORE_REVIEW:
            errs.append("first_paid_buyer_max_buyers")
    mode = facilitator_mode()
    if mode == "blocked":
        errs.append("mainnet_payment_disabled")
    if mode == "cdp" and not cdp_auth_configured():
        errs.append("cdp_facilitator_auth_missing")
    return errs


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
    pay_to = seller_receive_address() if valid_seller_receive_address() else ""
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
                "network": configured_network(),
                "amount": atomic_amount(),
                "asset": configured_asset(),
                "payTo": pay_to,
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
    try:
        raw = base64.b64decode(s, validate=False)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    try:
        return json.loads(s)
    except Exception:
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


def _503(blockers: list[str]) -> JSONResponse:
    return JSONResponse(
        {
            "error": "payment_misconfigured",
            "error_class": "paid_route_unavailable",
            "paid_route": "/v1/json/reliable",
            "blockers": blockers,
            "free_routes_operational": True,
        },
        status_code=503,
    )


def _facilitator_post(kind: str, payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Live verify/settle. Never called when flags are off or mock mode. Never logs secrets."""
    if kind not in {"verify", "settle"}:
        return {"ok": False, "error": "bad_kind"}
    name = selected_facilitator()
    headers: dict[str, str] = {"Content-Type": "application/json", "User-Agent": "agent-json-reliability-x402"}
    if name == "cdp":
        path = VERIFY_PATH if kind == "verify" else SETTLE_PATH
        auth, err = auth_headers("POST", path)
        if not auth:
            return {"ok": False, "error": err or "cdp_jwt_missing", "is_real": False}
        headers.update(auth)
    url = facilitator_base_url().rstrip("/") + f"/{kind}"
    body = json.dumps(
        {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": requirements.get("accepts", [{}])[0]}
    ).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        return {"ok": True, "data": data, "is_real": True, "facilitator": facilitator_base_url()}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http_{e.code}", "is_real": False}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": type(e).__name__, "is_real": False}


def probe_facilitator_supported() -> dict[str, Any]:
    """Safe reachability probe. No payment payload. Does not settle."""
    base = facilitator_base_url()
    url = base.rstrip("/") + "/supported"
    headers: dict[str, str] = {"User-Agent": "agent-json-reliability-x402-precheck"}
    authenticated = False
    auth_err = None
    if selected_facilitator() == "cdp" and cdp_auth_configured():
        auth, err = auth_headers("GET", SUPPORTED_PATH)
        if auth:
            headers.update(auth)
            headers.pop("Content-Type", None)
            authenticated = True
        else:
            auth_err = err
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = int(resp.status)
        return {
            "reachable": True,
            "http_status": code,
            "facilitator": base,
            "authenticated_probe": authenticated,
            "auth_error": auth_err,
        }
    except urllib.error.HTTPError as e:
        return {
            "reachable": e.code in {200, 400, 401, 403, 404, 405},
            "http_status": e.code,
            "facilitator": base,
            "authenticated_probe": authenticated,
            "auth_error": "unauthorized" if e.code == 401 else auth_err,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "reachable": False,
            "http_status": None,
            "facilitator": base,
            "authenticated_probe": authenticated,
            "auth_error": type(e).__name__,
        }


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
        "facilitator": facilitator_base_url(),
        "data": out.get("data"),
    }


def settle_payment(verified: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    mode = facilitator_mode()
    if mode == "off":
        return {"settlement_status": "skipped_flag_off", "tx_hash": None, "is_real": False}
    if verified.get("verify_status") == "replay_rejected":
        return {"settlement_status": "replay_rejected", "tx_hash": None, "is_real": False}
    if mode == "mock":
        return {
            "settlement_status": "mock_settled",
            "tx_hash": None,
            "is_real": False,
            "payer": verified.get("payer"),
            "payTo": seller_receive_address(),
            "network": configured_network(),
            "asset": "USDC",
            "amount": atomic_amount(),
            "price": str(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC),
            "note": "MOCK_NOT_REAL_SETTLEMENT",
            "payment_hash": verified.get("payment_hash"),
            "nonce": verified.get("nonce"),
            "verify_status": verified.get("verify_status"),
        }
    if mode not in {"cdp", "payai", "dexter"} or payload is None:
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
        "payTo": seller_receive_address(),
        "network": configured_network(),
        "asset": "USDC",
        "amount": atomic_amount(),
        "price": str(os.environ.get("PAID_PRICE_USDC") or PAID_PRICE_USDC),
        "payment_hash": verified.get("payment_hash"),
        "nonce": verified.get("nonce"),
        "verify_status": verified.get("verify_status"),
        "facilitator": facilitator_base_url(),
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
    blockers = paid_route_blockers()
    if blockers:
        return _503(blockers)
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
