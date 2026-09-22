"""CDP facilitator JWT (Ed25519). Never logs secrets. Not a wallet key."""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from typing import Any

CDP_HOST = "api.cdp.coinbase.com"
VERIFY_PATH = "/platform/v2/x402/verify"
SETTLE_PATH = "/platform/v2/x402/settle"
SUPPORTED_PATH = "/platform/v2/x402/supported"


def cdp_api_key_id() -> str:
    return (os.environ.get("CDP_API_KEY_ID") or "").strip()


def cdp_api_key_secret_present() -> bool:
    return bool((os.environ.get("CDP_API_KEY_SECRET") or "").strip())


def cdp_auth_configured() -> bool:
    return bool(cdp_api_key_id() and cdp_api_key_secret_present())


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_cdp_jwt(method: str, request_path: str, host: str = CDP_HOST) -> tuple[str | None, str | None]:
    """Return (jwt, error_code). error_code never includes secret material."""
    key_id = cdp_api_key_id()
    secret = (os.environ.get("CDP_API_KEY_SECRET") or "").strip()
    if not key_id or not secret:
        return None, "cdp_api_credentials_missing"
    if secret.startswith("-----BEGIN"):
        return None, "cdp_jwt_ecdsa_pem_unsupported_use_ed25519_api_key"
    try:
        raw = base64.b64decode(secret, validate=False)
    except Exception:
        return None, "cdp_jwt_secret_not_base64"
    if len(raw) < 32:
        return None, "cdp_jwt_secret_too_short"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return None, "cryptography_not_installed"
    try:
        key = Ed25519PrivateKey.from_private_bytes(raw[:32])
        now = int(time.time())
        header: dict[str, Any] = {
            "alg": "EdDSA",
            "typ": "JWT",
            "kid": key_id,
            "nonce": secrets.token_hex(16),
        }
        payload: dict[str, Any] = {
            "sub": key_id,
            "iss": "cdp",
            "aud": ["cdp_service"],
            "nbf": now,
            "exp": now + 120,
            "uri": f"{method.upper()} {host}{request_path}",
        }
        signing_input = (
            f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
            f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
        )
        sig = key.sign(signing_input.encode("ascii"))
        return f"{signing_input}.{_b64url(sig)}", None
    except Exception:
        return None, "cdp_jwt_sign_failed"


def auth_headers(method: str, request_path: str) -> tuple[dict[str, str] | None, str | None]:
    jwt, err = generate_cdp_jwt(method, request_path)
    if not jwt:
        return None, err
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}, None
