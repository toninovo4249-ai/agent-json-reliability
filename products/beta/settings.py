from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BETA_VERSION = "0.1.0"
STATUS = "BETA"


def _b(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def current_base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("BASE_URL") or "http://127.0.0.1:8770").rstrip("/")


def is_https_public(url: str | None = None) -> bool:
    u = (url or current_base_url()).lower()
    return u.startswith("https://") and "127.0.0.1" not in u and "localhost" not in u


def public_exposure_mode(url: str | None = None) -> str:
    u = (url or current_base_url()).lower()
    if "trycloudflare.com" in u:
        return "DEVELOPMENT_TEMPORARY"
    if is_https_public(u):
        return "DEVELOPMENT_TEMPORARY"
    return "LOCAL_ONLY"


PUBLIC_BETA_CONFIRM = _b("PUBLIC_BETA_CONFIRM", False)
_explicit_enabled = os.environ.get("PUBLIC_BETA_ENABLED")
if _explicit_enabled is not None and _explicit_enabled.strip() != "":
    PUBLIC_BETA_ENABLED = _b("PUBLIC_BETA_ENABLED", False)
else:
    PUBLIC_BETA_ENABLED = False
FREE_BETA = _b("FREE_BETA", True)
PAYMENT_REQUIRED = _b("PAYMENT_REQUIRED", False)
ENABLE_HTML_BETA = False
BATCH_PUBLIC = _b("BATCH_PUBLIC", False)
MAX_REQUEST_BODY_BYTES = _i("MAX_REQUEST_BODY_BYTES", 262144)
MAX_JSON_DEPTH = _i("MAX_JSON_DEPTH", 64)
MAX_SCHEMA_DEPTH = _i("MAX_SCHEMA_DEPTH", 64)
MAX_REQUESTS_PER_MINUTE_PER_SESSION = _i("MAX_REQUESTS_PER_MINUTE_PER_SESSION", 30)
MAX_CONCURRENT_REQUESTS = _i("MAX_CONCURRENT_REQUESTS", 8)
REQUEST_TIMEOUT_SECONDS = _i("REQUEST_TIMEOUT_SECONDS", 5)
MAX_ARRAY_LEN = _i("MAX_ARRAY_LEN", 10000)
MAX_OBJECT_KEYS = _i("MAX_OBJECT_KEYS", 5000)
MAX_STRING_CHARS = _i("MAX_STRING_CHARS", 100000)
MAX_NODES = _i("MAX_JSON_NODES", 20000)
MAX_BATCH = _i("MAX_BATCH", 20)
PUBLIC_BASE_URL = current_base_url()
INTERNAL_UA = "agent-json-reliability-internal"
INTERNAL_HEADER = "x-ajr-internal"
PUBLIC_CHECK_HEADER = "x-ajr-public-check"
SYNTHETIC_HEADER = "x-synthetic-buyer"
DB_PATH = Path(os.environ.get("TELEMETRY_DB") or str(ROOT / "data" / "local_telemetry.sqlite"))
SECRET_DIR = Path(os.environ.get("SECRET_DIR") or str(ROOT / "data" / "secrets"))

PUBLIC_PATHS = {
    "/",
    "/health",
    "/ready",
    "/capabilities",
    "/openapi.json",
    "/.well-known/agent-services.json",
    "/robots.txt",
    "/llms.txt",
    "/AGENTS.md",
    "/v1/json/inspect",
    "/v1/json/validate",
    "/v1/json/repair",
    "/v1/json/reliable",
    "/mcp",
}

TOOL_PATHS = {
    "/v1/json/inspect",
    "/v1/json/validate",
    "/v1/json/repair",
    "/v1/json/reliable",
}
