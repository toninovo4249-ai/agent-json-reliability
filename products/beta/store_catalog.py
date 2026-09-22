"""Free catalog + deterministic product routing. No LLM. No payment."""
from __future__ import annotations

import re
from typing import Any

from products.beta.product_registry import PRODUCTS, active_paid_products, product_paid_enabled

URL = {
    "type": "object",
    "properties": {"url": {"type": "string", "description": "Public http(s) URL"}},
    "required": ["url"],
}
URLS = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "urls": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    },
}
URLS2 = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "urls": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
    },
    "required": ["urls"],
}

# Distinct routing metadata. Prices stay in PRODUCTS.
META: dict[str, dict[str, Any]] = {
    "json_reliable": {
        "use_when": "Agent JSON is malformed, uses single quotes, or needs safe repair plus schema validation.",
        "output_summary": "valid_original, repaired, valid_final, json, errors, changes. Never invents missing values.",
        "keywords": ["malformed json", "repair json", "json reliability", "trailing comma", "single quotes", "schema validation"],
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "Malformed or valid JSON text"},
                "schema": {"type": "object", "description": "Optional JSON Schema"},
            },
        },
    },
    "json_contract_check": {
        "use_when": "You already have JSON and a JSON Schema and need missing keys, extra keys, and type mismatches.",
        "output_summary": "valid, schema violations, missing_keys, additional_keys, type_mismatches.",
        "keywords": ["json schema", "contract check", "missing keys", "additional properties", "type mismatch"],
        "input_schema": {
            "type": "object",
            "required": ["json"],
            "properties": {
                "json": {"description": "Document to check"},
                "document": {"description": "Alias for json"},
                "schema": {"type": "object"},
            },
        },
    },
    "json_diff": {
        "use_when": "Compare two JSON documents for added/removed keys, type changes, and value changes.",
        "output_summary": "added_keys, removed_keys, changed_types, changed_values, structural_compatibility.",
        "keywords": ["json diff", "structural diff", "before after", "breaking json change"],
        "input_schema": {
            "type": "object",
            "required": ["before", "after"],
            "properties": {"before": {}, "after": {}},
        },
    },
    "web_extract": {
        "use_when": "Need title, headings, main text, and metadata from one public HTML page.",
        "output_summary": "title, headings, main_text, metadata, structured_sections, provenance.",
        "keywords": ["extract webpage", "page text", "headings", "html extract", "structured content"],
        "input_schema": URL,
    },
    "web_markdown": {
        "use_when": "Convert a public HTML page into deterministic Markdown with a content hash.",
        "output_summary": "markdown, source_url, timestamp, sha256.",
        "keywords": ["html to markdown", "clean markdown", "page markdown"],
        "input_schema": URL,
    },
    "web_tables": {
        "use_when": "Extract HTML tables into columns and rows from a public URL.",
        "output_summary": "tables[] with columns, rows, source indexes, provenance.",
        "keywords": ["table extraction", "html table", "structured rows", "spreadsheet html"],
        "input_schema": URL,
    },
    "web_metadata": {
        "use_when": "Need OpenGraph, Twitter cards, canonical, JSON-LD, or favicon without full page text.",
        "output_summary": "title, description, canonical, opengraph, twitter, json_ld, language, favicon.",
        "keywords": ["opengraph", "twitter card", "json-ld", "canonical url", "page metadata"],
        "input_schema": URL,
    },
    "web_link_map": {
        "use_when": "Map internal vs external links on a public page.",
        "output_summary": "internal, external, invalid patterns, counts, provenance.",
        "keywords": ["link map", "internal links", "external links", "outbound urls"],
        "input_schema": URL,
    },
    "evidence_pack": {
        "use_when": "Need a fresh multi-URL evidence pack with SHA-256 provenance and contradictions.",
        "output_summary": "facts, sources, contradictions, confidence, warnings. Winner not invented.",
        "keywords": ["evidence pack", "fresh fetch", "provenance", "sha-256", "contradictions"],
        "input_schema": URLS,
    },
    "evidence_compare": {
        "use_when": "Compare two to five public sources for agreements and differences.",
        "output_summary": "agreements, differences, contradictions, sources. winner is always null unless deterministic.",
        "keywords": ["compare sources", "multi source", "agreement", "web compare"],
        "input_schema": URLS2,
    },
    "evidence_contradictions": {
        "use_when": "Find conflicting claims across two to five URLs without picking a winner.",
        "output_summary": "contradiction_groups with claims, values, sources, timestamps. winner=null.",
        "keywords": ["contradiction scan", "conflicting claims", "source conflict"],
        "input_schema": URLS2,
    },
    "evidence_freshness": {
        "use_when": "Prove when a public URL was fetched and whether cache validators exist.",
        "output_summary": "fetched_at, last_modified, etag, content_hash, cache_headers.",
        "keywords": ["freshness", "last-modified", "etag", "cache headers", "content hash"],
        "input_schema": URL,
    },
    "evidence_receipt": {
        "use_when": "Need a provenance receipt (status, type, SHA-256, headers) without storing the body.",
        "output_summary": "url, timestamp, http_status, content_type, sha256, headers. body_stored=false.",
        "keywords": ["provenance receipt", "content hash receipt", "no body stored"],
        "input_schema": URL,
    },
    "url_preflight": {
        "use_when": "Production-readiness check of a public origin: TLS, headers, robots, OpenAPI, sitemap, localhost leaks.",
        "output_summary": "tls, headers, redirects, robots, openapi, sitemap, localhost_leaks, timestamp.",
        "keywords": ["url preflight", "production ready", "site audit", "localhost leak"],
        "input_schema": URL,
    },
    "url_security_headers": {
        "use_when": "Audit HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, frame protections.",
        "output_summary": "present, missing, selected security headers, provenance.",
        "keywords": ["security headers", "hsts", "csp", "x-content-type-options", "frame options"],
        "input_schema": URL,
    },
    "url_cors_check": {
        "use_when": "Detect wildcard CORS, credential conflicts, and preflight behavior.",
        "output_summary": "allow_origin, wildcard, credential_wildcard_conflict, preflight_status.",
        "keywords": ["cors", "wildcard origin", "access-control-allow-origin", "preflight"],
        "input_schema": {
            "type": "object",
            "required": ["url"],
            "properties": {"url": {"type": "string"}, "origin": {"type": "string"}},
        },
    },
    "url_tls_check": {
        "use_when": "Inspect TLS availability, certificate subject, issuer, expiry, and hostname match.",
        "output_summary": "tls_available, protocol, subject, issuer, not_after, hostname_match.",
        "keywords": ["tls", "certificate", "ssl expiry", "hostname match"],
        "input_schema": URL,
    },
    "url_robots_audit": {
        "use_when": "Check robots.txt, llms.txt, AGENTS.md, sitemap, and agent-readable metadata.",
        "output_summary": "presence and hashes for robots, llms.txt, AGENTS.md, sitemap, agent.json.",
        "keywords": ["robots.txt", "llms.txt", "agents.md", "sitemap", "agent access"],
        "input_schema": URL,
    },
    "url_redirect_check": {
        "use_when": "Audit redirect hops, protocol downgrade, loops, and the final URL.",
        "output_summary": "hops, status_codes, domains, protocol_downgrade, loops, final_url.",
        "keywords": ["redirect chain", "http downgrade", "redirect loop", "final url"],
        "input_schema": URL,
    },
    "api_openapi_audit": {
        "use_when": "Audit an OpenAPI document for syntax, servers, security, and localhost URLs.",
        "output_summary": "operation_count, missing_descriptions, localhost_urls, issues.",
        "keywords": ["openapi audit", "swagger audit", "localhost server", "api spec"],
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "spec": {"type": "object"}},
        },
    },
    "api_openapi_diff": {
        "use_when": "Diff two OpenAPI specs for removed endpoints and other breaking changes.",
        "output_summary": "removed_endpoints, required_field_changes, type_changes, security_changes, breaking.",
        "keywords": ["openapi diff", "breaking change", "removed endpoint", "api compatibility"],
        "input_schema": {
            "type": "object",
            "properties": {
                "old": {"type": "object"},
                "new": {"type": "object"},
                "old_url": {"type": "string"},
                "new_url": {"type": "string"},
            },
        },
    },
    "api_schema_drift": {
        "use_when": "Compare a live GET/HEAD JSON response shape to a declared schema. No destructive methods.",
        "output_summary": "observed_shape, declared_schema, http_status. GET/HEAD only.",
        "keywords": ["schema drift", "live vs spec", "response shape", "openapi drift"],
        "input_schema": {
            "type": "object",
            "required": ["live_url"],
            "properties": {
                "live_url": {"type": "string"},
                "endpoint": {"type": "string"},
                "schema": {"type": "object"},
                "openapi_url": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "HEAD"]},
            },
        },
    },
    "mcp_preflight": {
        "use_when": "Check a remote MCP server with initialize and tools/list only. Does not execute tools.",
        "output_summary": "initialize ok, tools_list, tool_schemas, server_info. tools_executed=false.",
        "keywords": ["mcp preflight", "tools/list", "mcp initialize", "mcp production"],
        "input_schema": URL,
    },
    "x402_preflight": {
        "use_when": "Validate that a paid HTTP endpoint returns a correct unpaid x402 402 challenge. Never pays.",
        "output_summary": "http_status, network, asset, amount, payTo, scheme, discovery. payment_signature_sent=false.",
        "keywords": ["x402 validation", "payment challenge", "production readiness", "402 probe", "payment-required"],
        "input_schema": {
            "type": "object",
            "required": ["url"],
            "properties": {"url": {"type": "string"}, "endpoint": {"type": "string"}},
        },
    },
}

DESC_LIMIT = 200

EXAMPLE_IO: dict[str, dict[str, Any]] = {
    "json_reliable": {"input": {"text": "{'a': 1}"}, "output": {"valid_original": False, "repaired": True, "valid_final": True, "json": {"a": 1}}},
    "json_contract_check": {"input": {"json": {"a": 1}, "schema": {"type": "object"}}, "output": {"valid": True, "missing_keys": [], "additional_keys": []}},
    "json_diff": {"input": {"before": {"a": 1}, "after": {"a": 2}}, "output": {"changed_values": [{"path": "a"}], "structural_compatibility": True}},
    "web_extract": {"input": {"url": "https://example.com/"}, "output": {"title": "Example", "headings": [], "main_text": "", "provenance": {}}},
    "web_markdown": {"input": {"url": "https://example.com/"}, "output": {"markdown": "# Example", "sha256": "", "source_url": "https://example.com/"}},
    "web_tables": {"input": {"url": "https://example.com/"}, "output": {"tables": [{"columns": [], "rows": []}]}},
    "web_metadata": {"input": {"url": "https://example.com/"}, "output": {"title": "Example", "canonical": "https://example.com/", "opengraph": {}}},
    "web_link_map": {"input": {"url": "https://example.com/"}, "output": {"internal": [], "external": [], "counts": {}}},
    "evidence_pack": {"input": {"urls": ["https://example.com/"]}, "output": {"facts": [], "sources": [], "contradictions": [], "winner": None}},
    "evidence_compare": {"input": {"urls": ["https://example.com/", "https://example.org/"]}, "output": {"agreements": [], "differences": [], "winner": None}},
    "evidence_contradictions": {"input": {"urls": ["https://example.com/", "https://example.org/"]}, "output": {"contradiction_groups": [], "winner": None}},
    "evidence_freshness": {"input": {"url": "https://example.com/"}, "output": {"fetched_at": "", "etag": None, "content_hash": ""}},
    "evidence_receipt": {"input": {"url": "https://example.com/"}, "output": {"http_status": 200, "sha256": "", "body_stored": False}},
    "url_preflight": {"input": {"url": "https://example.com/"}, "output": {"tls": {}, "headers": {}, "localhost_leaks": []}},
    "url_security_headers": {"input": {"url": "https://example.com/"}, "output": {"present": [], "missing": []}},
    "url_cors_check": {"input": {"url": "https://example.com/", "origin": "https://agent.example"}, "output": {"wildcard": False, "allow_origin": None}},
    "url_tls_check": {"input": {"url": "https://example.com/"}, "output": {"tls_available": True, "hostname_match": True}},
    "url_robots_audit": {"input": {"url": "https://example.com/"}, "output": {"robots": True, "llms_txt": False, "sitemap": False}},
    "url_redirect_check": {"input": {"url": "https://example.com/"}, "output": {"hops": [], "final_url": "https://example.com/", "loops": False}},
    "api_openapi_audit": {"input": {"url": "https://example.com/openapi.json"}, "output": {"operation_count": 0, "localhost_urls": [], "issues": []}},
    "api_openapi_diff": {"input": {"old_url": "https://example.com/openapi.json", "new_url": "https://example.com/openapi.json"}, "output": {"removed_endpoints": [], "breaking": False}},
    "api_schema_drift": {"input": {"live_url": "https://example.com/health", "method": "GET"}, "output": {"http_status": 200, "observed_shape": {}}},
    "mcp_preflight": {"input": {"url": "https://example.com/mcp"}, "output": {"tools_list": [], "tools_executed": False}},
    "x402_preflight": {"input": {"url": "https://example.com/paid"}, "output": {"http_status": 402, "payment_signature_sent": False}},
}

TASK_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("cors",), "url_cors_check", "CORS / Access-Control check"),
    (("extract tables", "html table", "tables"), "web_tables", "Extract HTML tables"),
    (("repair json", "malformed json", "fix json", "repair json"), "json_reliable", "Repair malformed JSON"),
    (("validate x402", "x402 endpoint", "402 challenge", "payment-required"), "x402_preflight", "Validate unpaid x402 402"),
    (("compare two urls", "compare two url", "compare urls", "compare two web"), "evidence_compare", "Compare two public URLs"),
    (("openapi breaking", "breaking changes", "openapi diff", "removed endpoint"), "api_openapi_diff", "OpenAPI breaking-change diff"),
)


def merged(prod: dict[str, Any]) -> dict[str, Any]:
    extra = META.get(prod["id"]) or {}
    out = dict(prod)
    out.update(extra)
    return out


def catalog_item(prod: dict[str, Any]) -> dict[str, Any]:
    p = merged(prod)
    io = EXAMPLE_IO.get(p["id"]) or {"input": {}, "output": {"ok": True}}
    out_schema = p.get("output_schema") or {"type": "object", "description": p.get("output_summary") or "JSON object"}
    return {
        "product_id": p["id"],
        "name": p["name"],
        "category": p["category"],
        "endpoint": p["path"],
        "path": p["path"],
        "method": "POST",
        "price_usdc": float(p["price_usdc"]),
        "price": str(p["price_usdc"]),
        "price_atomic": int(p["price_atomic"]),
        "network": "eip155:8453",
        "asset": "USDC",
        "description": (p["description"] or "")[:DESC_LIMIT],
        "use_when": p.get("use_when") or p["purpose"],
        "output_summary": p.get("output_summary") or "",
        "keywords": list(p.get("keywords") or []),
        "input_schema": p.get("input_schema") or {"type": "object"},
        "output_schema": out_schema,
        "example_input": io.get("input") or {},
        "example_output": io.get("output") or {"ok": True},
        "x402": True,
        "paid_enabled": product_paid_enabled(p),
    }


def bazaar_info(prod: dict[str, Any]) -> dict[str, Any]:
    item = catalog_item(prod)
    return {
        "bazaar": {
            "info": {
                "description": item["description"],
                "category": item["category"],
                "path": item["path"],
                "method": "POST",
                "network": item["network"],
                "asset": item["asset"],
                "price": item["price"],
                "input": {
                    "type": "http",
                    "method": "POST",
                    "discoverable": True,
                    "bodyType": "json",
                    "queryParams": {},
                    "bodySchema": item["input_schema"],
                },
                "output": {
                    "type": "json",
                    "schema": item["output_schema"],
                    "example": item["example_output"],
                },
            }
        }
    }


def validate_bazaar_metadata() -> list[str]:
    needed = (
        "description",
        "input_schema",
        "output_schema",
        "example_output",
        "price",
        "method",
        "path",
        "network",
        "asset",
        "category",
    )
    missing: list[str] = []
    for p in PRODUCTS:
        item = catalog_item(p)
        for k in needed:
            if item.get(k) in (None, "", [], {}):
                missing.append(f"{p['id']}.{k}")
        if len(str(item.get("description") or "")) > DESC_LIMIT:
            missing.append(f"{p['id']}.description_too_long")
        bazaar_info(p)
    return missing


def catalog_payload() -> dict[str, Any]:
    items = [catalog_item(p) for p in PRODUCTS]
    return {
        "name": "Agent Utility Store",
        "protocol": "x402",
        "network": "eip155:8453",
        "asset": "USDC",
        "pay_per_call": True,
        "llm_required": False,
        "free_routes": [
            "/v1/json/inspect",
            "/v1/json/validate",
            "/v1/json/repair",
            "/mcp",
            "/v1/catalog",
            "/v1/catalog/select",
            "/skill.md",
        ],
        "catalog": "/v1/catalog",
        "selector": "/v1/catalog/select",
        "skill": "/skill.md",
        "product_count": len(items),
        "bazaar_metadata_pass": not validate_bazaar_metadata(),
        "products": items,
    }


def select_products(task: str, limit: int = 3) -> dict[str, Any]:
    raw = (task or "").strip()
    if not raw:
        raise ValueError("task_required")
    t = raw.lower()
    tokens = set(re.findall(r"[a-z0-9+]{3,}", t))
    scored: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for p in PRODUCTS:
        m = merged(p)
        score = 0
        blob = " ".join(
            [
                m["id"].replace("_", " "),
                m["name"].lower(),
                m["category"],
                m["purpose"].lower(),
                m["description"].lower(),
                (m.get("use_when") or "").lower(),
                " ".join(m.get("keywords") or []),
            ]
        )
        for kw in m.get("keywords") or []:
            if kw.lower() in t:
                score += 8
        for tok in tokens:
            if tok in blob:
                score += 1
        scored[m["id"]] = score
    for needles, pid, reason in TASK_RULES:
        if any(n in t for n in needles):
            scored[pid] = scored.get(pid, 0) + 24
            reasons[pid] = reason
    extra = (
        (("malformed",), "json_reliable", "Repair malformed JSON"),
        (("compare", "source"), "evidence_compare", "Compare public sources"),
        (("x402",), "x402_preflight", "Validate unpaid x402 402"),
        (("table",), "web_tables", "Extract HTML tables"),
        (("cors",), "url_cors_check", "CORS check"),
        (("openapi",), "api_openapi_diff", "OpenAPI diff"),
    )
    for needles, pid, reason in extra:
        if all(n in t for n in needles) or (len(needles) == 1 and needles[0] in t):
            scored[pid] = scored.get(pid, 0) + 10
            reasons.setdefault(pid, reason)
    ranked_ids = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    if not any(sc > 0 for _, sc in ranked_ids):
        ranked_ids = [("json_reliable", 0)]
    top_n = [pid for pid, sc in ranked_ids if sc > 0][: max(1, limit)]
    if not top_n:
        top_n = [ranked_ids[0][0]]
    matches = []
    by_id = {p["id"]: p for p in PRODUCTS}
    for pid in top_n:
        item = catalog_item(by_id[pid])
        matches.append(
            {
                "product_id": pid,
                "name": item["name"],
                "reason": reasons.get(pid) or item["use_when"],
                "price": item["price"],
                "price_usdc": item["price_usdc"],
                "endpoint": item["endpoint"],
                "method": "POST",
                "input_example": item["example_input"],
                "score": scored.get(pid, 0),
            }
        )
    return {"task": raw, "matches": matches, "top": matches[0]["product_id"] if matches else None, "llm_used": False}


def winner_tier(buyers: int, calls: int, repeats: int) -> str:
    if buyers >= 5 and calls >= 25:
        return "C"
    if repeats >= 1:
        return "B"
    if buyers >= 1:
        return "A"
    return "none"
