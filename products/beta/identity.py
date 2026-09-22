from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from products.beta.settings import INTERNAL_HEADER, INTERNAL_UA, PUBLIC_CHECK_HEADER, SYNTHETIC_HEADER, SECRET_DIR

CRAWLER_HINTS = (
    "googlebot",
    "bingbot",
    "yandex",
    "baiduspider",
    "duckduckbot",
    "applebot",
    "amazonbot",
    "facebookexternalhit",
    "twitterbot",
    "slackbot",
    "discordbot",
    "ahrefs",
    "semrush",
    "bytespider",
    "gptbot",
    "claudebot",
    "petalbot",
    "crawler",
    "spider",
    "scrapy",
)

MCP_REGISTRY_HINTS = (
    "mcp-publisher",
    "modelcontextprotocol",
    "official mcp",
    "mcp registry",
    "glama",
    "smithery",
    "pulsemcp",
    "mcp.so",
)

SEARCH_CRAWLER_HINTS = (
    "googlebot",
    "bingbot",
    "yandex",
    "baiduspider",
    "duckduckbot",
    "applebot",
    "amazonbot",
    "facebookexternalhit",
    "twitterbot",
    "slackbot",
    "discordbot",
    "ahrefs",
    "semrush",
    "bytespider",
    "gptbot",
    "claudebot",
    "petalbot",
    "google-inspectiontool",
    "bingpreview",
)

DIRECTORY_CRAWLER_HINTS = (
    "glama",
    "pulsemcp",
    "smithery",
    "mcp.so",
    "mcp-publisher",
    "modelcontextprotocol",
    "public-apis",
    "freeapis",
    "awesome-mcp",
    "mcpservers.org",
    "mcp.directory",
    "x402scan",
    "agentcash",
    "402index",
    "402 index",
    "402index.io",
    "indexnow",
    "payai",
    "lobehub",
    "uptimerobot",
    "betteruptime",
    "betterstack",
    "healthcheck",
    "kube-probe",
    "google-inspectiontool",
    "bingpreview",
    "duckduckbot",
)

DIRECTORY_SOURCES = {
    "x402scan",
    "402index",
    "indexnow",
    "payai",
    "circle",
    "bazaar",
}

SYNTHETIC_KINDS = {
    "SYNTHETIC",
    "SYNTHETIC_EXTERNAL_BUYER",
    "SYNTHETIC_BUYER",
    "INTERNAL_TEST",
    "INTERNAL_EXTERNAL_PATH_TEST",
    "KNOWN_SELF_TEST",
    "LOCALHOST",
}

DIRECTORY_KINDS = {
    "DIRECTORY_PROBE",
    "LIKELY_CRAWLER",
    "HEALTH_MONITOR",
    "HEALTH_CHECK",
}

SEARCH_KINDS = {"SEARCH_CRAWLER"}
MCP_KINDS = {"MCP_REGISTRY_PROBE"}

SELF_HINTS = (
    "x402-hunter",
    "cursor/",
    "cursor-ide",
    "render/",
)


SCANNER_HINTS = (
    "nmap",
    "nikto",
    "sqlmap",
    "masscan",
    "zgrab",
    "nuclei",
    "nessus",
    "openvas",
    "wpscan",
    "dirbuster",
    "gobuster",
    "zaproxy",
)

PROBE_PATHS = {
    "/favicon.ico",
    "/favicon.png",
    "/robots.txt.bak",
    "/.env",
    "/wp-admin",
    "/wp-login.php",
    "/admin",
    "/phpinfo.php",
    "/.git",
    "/server-status",
}


def _daily_secret() -> bytes:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = SECRET_DIR / f"{day}.key"
    if not path.exists():
        path.write_bytes(hashlib.sha256(os_urandom()).digest())
    return path.read_bytes()


def os_urandom() -> bytes:
    import os

    return os.urandom(32)


def ip_prefix(ip: str | None) -> str:
    if not ip:
        return "none"
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:3]) + "::"
    bits = ip.split(".")
    if len(bits) == 4:
        return ".".join(bits[:3]) + ".0"
    return "invalid"


def ua_coarse(ua: str | None) -> tuple[str, float]:
    s = (ua or "").lower()
    if INTERNAL_UA in s or "pytest" in s or "testclient" in s:
        return "INTERNAL_TEST", 0.99
    if any(x in s for x in SCANNER_HINTS) and "python-httpx" not in s:
        return "SECURITY_SCANNER", 0.7
    if any(x in s for x in CRAWLER_HINTS):
        return "LIKELY_CRAWLER", 0.7
    if "mcp" in s:
        return "MCP_CLIENT", 0.6
    if any(x in s for x in ("curl", "wget", "httpie", "python-requests", "aiohttp", "go-http")):
        return "SCRIPT", 0.55
    if any(x in s for x in ("agent", "openai", "anthropic", "claude", "gpt", "langchain")):
        return "AI_AGENT_LIKELY", 0.35
    if "mozilla" in s or "chrome" in s or "safari" in s:
        return "HUMAN_BROWSER", 0.45
    return "UNKNOWN", 0.2


def client_hash(ip: str | None, ua: str | None) -> str:
    msg = f"{ip_prefix(ip)}|{ua_coarse(ua)[0]}".encode()
    return hmac.new(_daily_secret(), msg, hashlib.sha256).hexdigest()[:20]


def traffic_kind(
    headers: Any,
    ua: str | None,
    client_host: str | None,
    path: str | None = None,
    source: str | None = None,
) -> str:
    """Audience class. Only REAL_EXTERNAL_UNKNOWN may count as demand."""
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    ual = (ua or "").lower()
    src = (source or h.get("x-discovery-source") or "").strip().lower()
    if h.get(PUBLIC_CHECK_HEADER) in {"1", "true"}:
        return "SYNTHETIC"
    if h.get(INTERNAL_HEADER) == "1" or INTERNAL_UA in ual:
        return "SYNTHETIC"
    if "pytest" in ual or "testclient" in ual:
        return "SYNTHETIC"
    if h.get(SYNTHETIC_HEADER) in {"1", "true"}:
        return "SYNTHETIC"
    if any(x in ual for x in SELF_HINTS):
        return "SYNTHETIC"
    if src in DIRECTORY_SOURCES:
        return "DIRECTORY_PROBE"
    if any(x in ual for x in SCANNER_HINTS) and "python-httpx" not in ual:
        return "SECURITY_SCAN"
    if any(x in ual for x in MCP_REGISTRY_HINTS):
        return "MCP_REGISTRY_PROBE"
    if any(x in ual for x in SEARCH_CRAWLER_HINTS):
        return "SEARCH_CRAWLER"
    if any(x in ual for x in DIRECTORY_CRAWLER_HINTS) or any(x in ual for x in CRAWLER_HINTS):
        return "DIRECTORY_PROBE"
    if path in PROBE_PATHS:
        return "RANDOM_PROBE"
    if (client_host or "") in {"127.0.0.1", "::1", "testclient", "localhost"}:
        return "SYNTHETIC"
    if path in {"/health", "/ready"} and (not ual or "health" in ual or "uptime" in ual or "monitor" in ual or "render" in ual):
        return "DIRECTORY_PROBE"
    return "REAL_EXTERNAL_AGENT"


def traffic_class(kind: str | None) -> str:
    k = kind or ""
    if k in SYNTHETIC_KINDS or k == "SYNTHETIC":
        return "SYNTHETIC"
    if k in SEARCH_KINDS:
        return "SEARCH_CRAWLER"
    if k in MCP_KINDS:
        return "MCP_REGISTRY_PROBE"
    if k in DIRECTORY_KINDS or k == "DIRECTORY_PROBE":
        return "DIRECTORY_PROBE"
    if k in {"SECURITY_SCAN", "RANDOM_PROBE"}:
        return "DIRECTORY_PROBE"
    if k in {"REAL_EXTERNAL_UNKNOWN", "REAL_EXTERNAL_AGENT"}:
        return "REAL_EXTERNAL_AGENT"
    return "DIRECTORY_PROBE"


def is_real_unknown(kind: str | None) -> bool:
    return traffic_class(kind) == "REAL_EXTERNAL_AGENT"
