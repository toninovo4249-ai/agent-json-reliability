"""Machine discovery surface map. No paid calls. No retry-window waits."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HOST = "https://agent-json-reliability.onrender.com"

SURFACES: tuple[dict[str, Any], ...] = (
    {
        "id": "circle_discovery",
        "name": "Circle Discovery API",
        "url": "https://api.circle.com/v2/x402/discovery/resources",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
        "note": "Do not resubmit unless Circle asks.",
    },
    {
        "id": "x402scan",
        "name": "x402scan",
        "url": "https://www.x402scan.com/server/d2c42ff7-e53e-4590-83eb-24fe022143f1",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
    },
    {
        "id": "payai_bazaar",
        "name": "PayAI Bazaar",
        "url": "https://facilitator.payai.network",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": True,
        "note": "Indexes after first real settle.",
    },
    {
        "id": "x402_facilitators",
        "name": "x402 Bazaar-compatible facilitators",
        "url": "https://facilitator.payai.network",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": True,
    },
    {
        "id": "402index",
        "name": "402 Index",
        "url": "https://402index.io",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": False,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
        "note": "10/hour. PENDING_RETRY, never sleep.",
    },
    {
        "id": "official_mcp_registry",
        "name": "Official MCP Registry",
        "url": "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.toninovo4249-ai%2Fagent-json-reliability",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
    },
    {
        "id": "glama",
        "name": "Glama",
        "url": "https://glama.ai/mcp/servers?query=agent-json-reliability",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
    },
    {
        "id": "x402_aggregators",
        "name": "x402 endpoint aggregators",
        "url": "https://www.x402scan.com",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
    },
    {
        "id": "indexnow",
        "name": "IndexNow",
        "url": "https://api.indexnow.org/indexnow",
        "QUERY_API_AVAILABLE": True,
        "AUTO_CRAWL_SUPPORTED": True,
        "MANUAL_LOGIN_REQUIRED": False,
        "REQUIRES_SETTLEMENT": False,
    },
)


def empty_row(spec: dict[str, Any], **extra: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": spec["id"],
        "name": spec["name"],
        "INDEXED": False,
        "SUBMITTED": False,
        "PENDING": False,
        "REQUIRES_SETTLEMENT": spec["REQUIRES_SETTLEMENT"],
        "MANUAL_LOGIN_REQUIRED": spec["MANUAL_LOGIN_REQUIRED"],
        "AUTO_CRAWL_SUPPORTED": spec["AUTO_CRAWL_SUPPORTED"],
        "QUERY_API_AVAILABLE": spec["QUERY_API_AVAILABLE"],
        "LAST_CHECKED_AT": now,
        "url": spec["url"],
        "note": spec.get("note"),
    }
    row.update(extra)
    return row
