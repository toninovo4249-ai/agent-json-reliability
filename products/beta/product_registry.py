"""Declarative 24-product Agent Utility Store. Prices for AJR/Evidence are fixed."""
from __future__ import annotations

import os
from typing import Any

# AJR 0.003 / 3000 and Evidence 0.0075 / 7500 must not change.
PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "id": "json_reliable",
        "name": "JSON Reliability",
        "path": "/v1/json/reliable",
        "category": "json",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "max_calls": 10,
        "max_buyers": 5,
        "existing": True,
        "purpose": "Inspect, safe repair, and JSON Schema validation.",
        "description": "Deterministic JSON inspect, safe repair, and optional JSON Schema validation.",
    },
    {
        "id": "json_contract_check",
        "name": "JSON Contract Check",
        "path": "/v1/json/contract-check",
        "category": "json",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Validate a document against JSON Schema with missing/extra key diagnostics.",
        "description": "JSON Schema contract check: valid, violations, missing keys, type mismatches, additional keys.",
    },
    {
        "id": "json_diff",
        "name": "JSON Structural Diff",
        "path": "/v1/json/diff",
        "category": "json",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Diff two JSON documents by keys, types, and values.",
        "description": "Structural JSON diff: added, removed, type changes, value changes, compatibility.",
    },
    {
        "id": "web_extract",
        "name": "Web Structured Extract",
        "path": "/v1/web/extract",
        "category": "web",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Extract title, headings, main text, and metadata from a public URL.",
        "description": "Public-URL structured extract with provenance (SHA-256, UTC).",
    },
    {
        "id": "web_markdown",
        "name": "Web Clean Markdown",
        "path": "/v1/web/markdown",
        "category": "web",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Convert a public page to deterministic Markdown.",
        "description": "Deterministic Markdown from a public URL with source, timestamp, SHA-256.",
    },
    {
        "id": "web_tables",
        "name": "Web Table Extract",
        "path": "/v1/web/tables",
        "category": "web",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Extract HTML tables from a public URL.",
        "description": "HTML table extract: columns, rows, source indexes, provenance.",
    },
    {
        "id": "web_metadata",
        "name": "Web Metadata Extract",
        "path": "/v1/web/metadata",
        "category": "web",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Extract title, canonical, OpenGraph, Twitter, and JSON-LD.",
        "description": "Page metadata: title, description, canonical, OpenGraph, Twitter, JSON-LD, language, favicon.",
    },
    {
        "id": "web_link_map",
        "name": "Web Link Map",
        "path": "/v1/web/link-map",
        "category": "web",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Map internal and external links on a public page.",
        "description": "Link map: internal, external, invalid patterns, canonicalized URLs, counts.",
    },
    {
        "id": "evidence_pack",
        "name": "Fresh Web Evidence Pack",
        "path": "/v1/evidence/pack",
        "category": "evidence",
        "price_usdc": "0.0075",
        "price_atomic": 7500,
        "max_calls": 20,
        "max_buyers": 10,
        "existing": True,
        "purpose": "Fetch up to 5 public URLs and return facts with provenance and contradictions.",
        "description": (
            "Fresh Web Evidence Pack for AI agents. "
            "Fetches up to 5 public URLs at request time and returns structured facts with source URLs, "
            "UTC timestamps, SHA-256 provenance, and explicit contradictions."
        ),
    },
    {
        "id": "evidence_compare",
        "name": "Multi-Source Evidence Compare",
        "path": "/v1/evidence/compare",
        "category": "evidence",
        "price_usdc": "0.01",
        "price_atomic": 10000,
        "purpose": "Compare 2–5 public sources for agreements and contradictions.",
        "description": "Compare 2–5 public URLs: agreements, differences, contradictions. Winner is null unless deterministic.",
    },
    {
        "id": "evidence_contradictions",
        "name": "Source Contradiction Scan",
        "path": "/v1/evidence/contradictions",
        "category": "evidence",
        "price_usdc": "0.0075",
        "price_atomic": 7500,
        "purpose": "Group conflicting claims across 2–5 URLs.",
        "description": "Contradiction groups across 2–5 URLs. No unsupported winner.",
    },
    {
        "id": "evidence_freshness",
        "name": "Freshness Proof",
        "path": "/v1/evidence/freshness",
        "category": "evidence",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Timestamp, cache headers, and content hash for a public URL.",
        "description": "Freshness proof: fetched_at, Last-Modified, ETag, SHA-256, cache headers.",
    },
    {
        "id": "evidence_receipt",
        "name": "Content Provenance Receipt",
        "path": "/v1/evidence/receipt",
        "category": "evidence",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Provenance receipt without storing page body.",
        "description": "Provenance receipt: URL, timestamp, status, content-type, SHA-256, selected headers. No body stored.",
    },
    {
        "id": "url_preflight",
        "name": "Public URL Preflight",
        "path": "/v1/url/preflight",
        "category": "url_security",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "TLS, headers, redirects, robots, OpenAPI, sitemap, localhost-leak warnings.",
        "description": "Public URL preflight: TLS, headers, redirects, robots, OpenAPI, sitemap, localhost leaks.",
    },
    {
        "id": "url_security_headers",
        "name": "Security Headers Audit",
        "path": "/v1/url/security-headers",
        "category": "url_security",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Audit HSTS, CSP, X-Content-Type-Options, Referrer-Policy, frame protections.",
        "description": "Security header audit for a public origin.",
    },
    {
        "id": "url_cors_check",
        "name": "CORS Configuration Check",
        "path": "/v1/url/cors-check",
        "category": "url_security",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Detect wildcard CORS, credential conflicts, and unsafe combinations.",
        "description": "CORS check: wildcard origins, credential conflicts, preflight behavior.",
    },
    {
        "id": "url_tls_check",
        "name": "TLS Snapshot",
        "path": "/v1/url/tls-check",
        "category": "url_security",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Certificate subject, issuer, expiry, and hostname match.",
        "description": "TLS snapshot: availability, subject, issuer, expiry, hostname match.",
    },
    {
        "id": "url_robots_audit",
        "name": "Robots / Agent Access Audit",
        "path": "/v1/url/robots-audit",
        "category": "url_security",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "Check robots.txt, llms.txt, AGENTS.md, sitemap, agent metadata.",
        "description": "Agent-access audit: robots.txt, llms.txt, AGENTS.md, sitemap.",
    },
    {
        "id": "url_redirect_check",
        "name": "Redirect Chain Audit",
        "path": "/v1/url/redirect-check",
        "category": "url_security",
        "price_usdc": "0.003",
        "price_atomic": 3000,
        "purpose": "List redirect hops, downgrades, loops, and final URL.",
        "description": "Redirect chain: hops, status codes, domains, protocol downgrade, loops, final URL.",
    },
    {
        "id": "api_openapi_audit",
        "name": "OpenAPI Production Audit",
        "path": "/v1/api/openapi-audit",
        "category": "api",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Audit an OpenAPI document for syntax, servers, security, localhost URLs.",
        "description": "OpenAPI audit: syntax, servers, operations, schemas, security, localhost URLs.",
    },
    {
        "id": "api_openapi_diff",
        "name": "OpenAPI Breaking Change Diff",
        "path": "/v1/api/openapi-diff",
        "category": "api",
        "price_usdc": "0.0075",
        "price_atomic": 7500,
        "purpose": "Diff two OpenAPI specs for breaking changes.",
        "description": "OpenAPI breaking-change diff: removed endpoints, methods, required fields, types, security.",
    },
    {
        "id": "api_schema_drift",
        "name": "API Schema Drift Check",
        "path": "/v1/api/schema-drift",
        "category": "api",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "Compare a live GET/HEAD response shape to a declared schema.",
        "description": "Schema drift: observed GET/HEAD JSON shape vs declared OpenAPI schema. No destructive methods.",
    },
    {
        "id": "mcp_preflight",
        "name": "MCP Production Preflight",
        "path": "/v1/mcp/preflight",
        "category": "mcp_x402",
        "price_usdc": "0.005",
        "price_atomic": 5000,
        "purpose": "initialize + tools/list against a remote MCP URL. Does not execute tools.",
        "description": "MCP preflight: initialize, tools/list, schemas, server info. Does not execute tools.",
    },
    {
        "id": "x402_preflight",
        "name": "x402 Production Preflight",
        "path": "/v1/x402/preflight",
        "category": "mcp_x402",
        "price_usdc": "0.0075",
        "price_atomic": 7500,
        "purpose": "Unpaid 402 probe of a paid endpoint. Never sends PAYMENT-SIGNATURE.",
        "description": "x402 unpaid preflight: HTTP 402, PAYMENT-REQUIRED, network, asset, amount, discovery. Never pays.",
    },
)

_BY_PATH = {p["path"]: p for p in PRODUCTS}
_BY_ID = {p["id"]: p for p in PRODUCTS}


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def product_by_path(path: str) -> dict[str, Any] | None:
    return _BY_PATH.get(path)


def product_by_id(pid: str) -> dict[str, Any] | None:
    return _BY_ID.get(pid)


def product_disabled(pid: str) -> bool:
    return _flag(f"PRODUCT_DISABLE_{pid.upper()}")


def product_paid_enabled(prod: dict[str, Any]) -> bool:
    if product_disabled(prod["id"]):
        return False
    if not (_flag("X402_PAYMENT_ENABLED") and _flag("PAID_ROUTE_ENABLED")):
        return False
    if prod["id"] == "evidence_pack":
        raw = os.environ.get("EVIDENCE_PAID_ROUTE_ENABLED")
        if raw is not None and str(raw).strip() != "":
            return _flag("EVIDENCE_PAID_ROUTE_ENABLED")
    return True


def active_paid_products() -> list[dict[str, Any]]:
    return [p for p in PRODUCTS if product_paid_enabled(p)]


def paid_paths() -> set[str]:
    return {p["path"] for p in active_paid_products()}


def max_calls(prod: dict[str, Any]) -> int:
    return int(prod.get("max_calls") or 20)


def max_buyers(prod: dict[str, Any]) -> int:
    return int(prod.get("max_buyers") or 10)
