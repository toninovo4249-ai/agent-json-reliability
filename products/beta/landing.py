from __future__ import annotations

from html import escape

from products.beta.settings import current_base_url, discovery_server_url, public_exposure_mode
from products.beta.x402_gate import payment_flags_on
from products.beta.product_registry import PRODUCTS, active_paid_products

INDEXNOW_KEY = "8f2c1a9e4b774d1e9c6a0b3d5e7f1021"

OPENAPI_DESCRIPTION = (
    "Agent JSON Reliability and Agent Utility Store. "
    "Free: inspect, validate, repair, MCP. "
    "Paid x402: POST /v1/json/reliable (0.003 USDC) and POST /v1/evidence/pack (0.0075 USDC) "
    "plus additional store utilities when enabled. "
    "Inspect, validate, repair, and MCP are not paid x402 endpoints."
)


def landing_html() -> str:
    shown = current_base_url()
    curl = (
        f"curl -s -X POST {shown}/v1/json/reliable \\\n"
        '  -H "content-type: application/json" \\\n'
        """  -d '{"text":"{'"'"'a'"'"': 1}"}'"""
    )
    py = (
        "import json, os, urllib.request\n"
        f"BASE = os.environ.get('PUBLIC_BASE_URL', '{shown}')\n"
        "req = urllib.request.Request(\n"
        "    BASE + '/v1/json/reliable',\n"
        "    data=json.dumps({'text': \"{'a': 1}\"}).encode(),\n"
        "    headers={'content-type': 'application/json'},\n"
        "    method='POST',\n"
        ")\n"
        "print(json.load(urllib.request.urlopen(req)))\n"
    )
    js = (
        f"const BASE = process.env.PUBLIC_BASE_URL || '{shown}';\n"
        "const r = await fetch(BASE + '/v1/json/reliable', {\n"
        "  method: 'POST',\n"
        "  headers: {'content-type': 'application/json'},\n"
        "  body: JSON.stringify({text: \"{'a': 1}\"}),\n"
        "});\n"
        "console.log(await r.json());\n"
    )
    notice = ""
    if public_exposure_mode() == "DEVELOPMENT_TEMPORARY":
        notice = (
            "<p><strong>PUBLIC_EXPOSURE_MODE=DEVELOPMENT_TEMPORARY</strong> "
            "— temporary HTTPS (for example Cloudflare Quick Tunnel). "
            "The URL may change between sessions. Not production hosting.</p>"
        )
    ld = json_ld_software()
    store = agent_utility_store_html()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reliable JSON for AI agents</title>
  <meta name="description" content="Deterministic JSON repair and JSON Schema validation for AI agents. Free MCP, inspect, validate, repair. Paid POST /v1/json/reliable 0.003 USDC via x402 on Base.">
  <link rel="canonical" href="{escape(shown)}/">
  <script type="application/ld+json">{ld}</script>
</head>
<body>
  <h1>Reliable JSON for AI agents</h1>
  <p>Agents frequently return malformed JSON.</p>
  <p>Deterministic inspect, safe repair, and JSON Schema validation. No LLM. No invented values.</p>
  <ul>
    <li>Free: MCP + inspect + validate + repair</li>
    <li>Paid: POST /v1/json/reliable — 0.003 USDC per call via x402 on Base</li>
  </ul>
  {notice}
  <p><strong>Before:</strong> <code>{{'name': 'agent',}}</code> (single quotes, trailing comma)</p>
  <p><strong>After:</strong> <code>{{"name": "agent"}}</code> — only if the repair is structurally safe. Missing semantic values are never invented.</p>
  <p>Primary: <code>POST {escape(shown)}/v1/json/reliable</code></p>
  {store}
  <p>Manifest: <a href="/.well-known/agent-services.json">/.well-known/agent-services.json</a>
     · OpenAPI: <a href="/openapi.json">/openapi.json</a>
     · <a href="/llms.txt">llms.txt</a> · <a href="/AGENTS.md">AGENTS.md</a>
     · <a href="/sitemap.xml">sitemap.xml</a>
     · <a href="/.well-known/agent.json">/.well-known/agent.json</a>
     · <a href="/.well-known/x402">/.well-known/x402</a>
     · <a href="/skill.md">/skill.md</a>
     · <a href="/v1/catalog">/v1/catalog</a></p>
  <h2>curl</h2>
  <pre>{escape(curl)}</pre>
  <h2>Python</h2>
  <pre>{escape(py)}</pre>
  <h2>JavaScript</h2>
  <pre>{escape(js)}</pre>
  <p>Optional self-reported source tags (unverified):
     <a href="/?source=github">?source=github</a>
     · <a href="/?source=x402scan">?source=x402scan</a>
     · <a href="/?source=community">?source=community</a>
     · <a href="/?source=showcase">?source=showcase</a>
     · <a href="/?source=mcp-registry">?source=mcp-registry</a>
     · <a href="/?source=direct">?source=direct</a></p>
</body>
</html>
"""


def agent_utility_store_html() -> str:
    cats = [
        ("json", "JSON"),
        ("web", "Web"),
        ("evidence", "Evidence"),
        ("url_security", "URL/Security"),
        ("api", "API/OpenAPI"),
        ("mcp_x402", "MCP/x402"),
    ]
    paid = {p["id"] for p in active_paid_products()} if payment_flags_on() else set()
    chunks = [
        "<h2>Agent Utility Store</h2>",
        "<p>Pay-per-call utilities for agents. Base USDC via x402. No subscription.</p>",
    ]
    for key, label in cats:
        chunks.append(f"<h3>{escape(label)}</h3><ul>")
        for p in PRODUCTS:
            if p["category"] != key:
                continue
            flag = "paid" if p["id"] in paid or (payment_flags_on() and p["id"] in paid) else ("paid" if payment_flags_on() else "listed")
            chunks.append(
                "<li>"
                f"<strong>{escape(p['name'])}</strong> — {escape(p['purpose'])} "
                f"({escape(str(p['price_usdc']))} USDC, <code>POST {escape(p['path'])}</code>)"
                "</li>"
            )
        chunks.append("</ul>")
    return "\n".join(chunks)


def agents_md() -> str:
    base = discovery_server_url()
    paid = payment_flags_on()
    pay_note = (
        "POST /v1/json/reliable is paid x402 exact 0.003 USDC on Base. "
        "POST /v1/evidence/pack is 0.0075 USDC. Additional Agent Utility Store routes are paid when listed in /.well-known/x402. "
        "inspect/validate/repair and MCP stay free."
        if paid
        else "Hosted payment flags are off: HTTP routes are free."
    )
    return f"""# Agent instructions

Agent JSON Reliability. llm_required=false. deterministic=true.

Free: inspect, validate, repair, MCP, GET /v1/catalog, POST /v1/catalog/select.
Paid hosted reliability endpoint: POST {base}/v1/json/reliable (0.003 USDC per call via x402 on Base when payment is enabled).

AI agents frequently emit malformed JSON. This API deterministically inspects, repairs and schema-validates JSON without another LLM call.

1. GET {base}/v1/catalog — list 24 paid products
2. POST {base}/v1/catalog/select {{"task": "<what you need>"}} — deterministic router, no LLM
3. GET {base}/.well-known/agent-services.json
4. Prefer capability json_reliable / POST {base}/v1/json/reliable for malformed JSON
5. Send {{"text": "<json or malformed json>", "schema": {{optional JSON Schema}}}}
6. Do not invent values if repaired=false
7. {pay_note}
8. Machine discovery: {base}/openapi.json {base}/.well-known/x402 {base}/.well-known/agent.json {base}/skill.md {base}/llms.txt {base}/v1/catalog

Limits: body 262144 bytes, depth 64, 30 requests/minute/session.
PyPI: uvx agent-json-reliability
MCP Registry: io.github.toninovo4249-ai/agent-json-reliability
GitHub: https://github.com/toninovo4249-ai/agent-json-reliability
"""


def llms_txt() -> str:
    base = discovery_server_url()
    paid = payment_flags_on()
    return (
        "# AGENT_JSON_RELIABILITY\n"
        "Agent JSON Reliability. AUTH NONE.\n"
        "Free: inspect, validate, repair, MCP.\n"
        "Paid hosted reliability endpoint: POST /v1/json/reliable "
        "(0.003 USDC per call via x402 on Base when payment is enabled).\n"
        "Paid evidence: POST /v1/evidence/pack (0.0075 USDC). Agent Utility Store additional paid routes: see /.well-known/x402.\n"
        "AI agents frequently emit malformed JSON. This API deterministically inspects, "
        "repairs and schema-validates JSON without another LLM call.\n"
        f"Primary: POST {base}/v1/json/reliable\n"
        "Capability: json_reliable\n"
        f"deterministic=true llm_required=false mixed_pricing={str(paid).lower()}\n"
        f"Catalog: {base}/v1/catalog\n"
        f"Select: POST {base}/v1/catalog/select {{\"task\":\"...\"}}\n"
        f"Skill: {base}/skill.md\n"
        f"Agent products: {base}/.well-known/agent-products.json\n"
        f"OpenAPI: {base}/openapi.json\n"
        f"x402: {base}/.well-known/x402\n"
        f"Agent card: {base}/.well-known/agent.json\n"
        f"MCP card: {base}/.well-known/mcp/server-card.json\n"
        f"Sitemap: {base}/sitemap.xml\n"
        f"Full: {base}/llms-full.txt\n"
        f"AGENTS.md: {base}/AGENTS.md\n"
        "PyPI: https://pypi.org/project/agent-json-reliability/\n"
        "GitHub: https://github.com/toninovo4249-ai/agent-json-reliability\n"
        "MCP: io.github.toninovo4249-ai/agent-json-reliability\n"
    )


def llms_full_txt() -> str:
    return (
        llms_txt()
        + "\n# Free HTTP\n"
        "POST /v1/json/inspect POST /v1/json/validate POST /v1/json/repair POST /mcp\n"
        "GET /v1/catalog POST /v1/catalog/select GET /skill.md GET /.well-known/agent-products.json\n"
        "# Paid HTTP\n"
        "24 x402 products in GET /v1/catalog and GET /openapi.json. "
        "POST /v1/json/reliable 0.003 USDC. POST /v1/evidence/pack 0.0075 USDC.\n"
        "# Router: POST /v1/catalog/select {\"task\":\"fix malformed JSON\"}\n"
        "# Do not invent JSON values when repaired=false\n"
    )


def robots_txt() -> str:
    base = discovery_server_url()
    bots = [
        "GPTBot",
        "ChatGPT-User",
        "ClaudeBot",
        "anthropic-ai",
        "Google-Extended",
        "PerplexityBot",
        "Applebot-Extended",
        "Bytespider",
        "CCBot",
        "Amazonbot",
    ]
    lines = ["User-agent: *", "Allow: /", "Disallow: /v16-", ""]
    for b in bots:
        lines.extend([f"User-agent: {b}", "Allow: /", ""])
    lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n".join(lines) + "\n"


def discovery_get_paths() -> list[str]:
    return [
        "/",
        "/health",
        "/openapi.json",
        "/llms.txt",
        "/llms-full.txt",
        "/AGENTS.md",
        "/robots.txt",
        "/sitemap.xml",
        "/.well-known/agent-services.json",
        "/.well-known/mcp/server-card.json",
        "/.well-known/x402",
        "/.well-known/agent.json",
        "/.well-known/agent-products.json",
        "/v1/catalog",
        "/skill.md",
        "/capabilities",
    ]


def sitemap_xml() -> str:
    base = discovery_server_url().rstrip("/")
    urls = "\n".join(f"  <url><loc>{base}{p}</loc></url>" for p in discovery_get_paths() if p != "/sitemap.xml")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


def skill_md() -> str:
    base = discovery_server_url().rstrip("/")
    return f"""# Agent Utility Store skill

Service: deterministic JSON + web/evidence/URL/OpenAPI utilities. No LLM.

Catalog: {base}/v1/catalog
Selector: POST {base}/v1/catalog/select {{"task":"<need>"}}
Skill: {base}/skill.md
OpenAPI: {base}/openapi.json
x402: {base}/.well-known/x402
Agent: {base}/.well-known/agent.json
Services: {base}/.well-known/agent-services.json
llms: {base}/llms.txt
AGENTS: {base}/AGENTS.md

Categories: json, web, evidence, url_security, api, mcp_x402 (24 paid POST routes).

Free discovery: GET catalog, POST select, GET skill.md, GET openapi.json, POST /mcp tools list_paid_products and select_paid_product.
Free work: POST {base}/v1/json/inspect|validate|repair

Paid: x402 exact on Base (eip155:8453) USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913.
Unpaid POST to a paid path returns HTTP 402 PAYMENT-REQUIRED. Send PAYMENT-SIGNATURE after facilitator verify. Work runs only after verify. AJR 0.003 USDC. Evidence Pack 0.0075 USDC.

Paid path pattern: POST {base}/v1/{{json|web|evidence|url|api|mcp|x402}}/...
Do not invent JSON values when repaired=false. Never send owner PAYMENT-SIGNATURE from this skill.
"""


def json_ld_software() -> str:
    import json as _json

    base = discovery_server_url().rstrip("/")
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "SoftwareApplication",
                "name": "Agent JSON Reliability",
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "Any",
                "url": base + "/",
                "description": "Deterministic JSON repair and JSON Schema validation for AI agents. No LLM.",
                "offers": {"@type": "Offer", "price": "0.003", "priceCurrency": "USD"},
                "softwareVersion": "0.1.0",
                "codeRepository": "https://github.com/toninovo4249-ai/agent-json-reliability",
            },
            {
                "@type": "WebAPI",
                "name": "Agent JSON Reliability HTTP API",
                "url": base + "/openapi.json",
                "documentation": base + "/llms.txt",
                "description": "Free inspect/validate/repair/MCP. Paid POST /v1/json/reliable via x402.",
            },
        ],
    }
    return _json.dumps(payload, separators=(",", ":"))


def well_known_agent_json() -> dict:
    base = discovery_server_url().rstrip("/")
    return {
        "schema_version": "1.0",
        "name": "Agent JSON Reliability",
        "description": "Deterministic inspect, safe repair, and JSON Schema validation. No LLM.",
        "homepage": base + "/",
        "openapi": base + "/openapi.json",
        "mcp": base + "/mcp",
        "catalog": base + "/v1/catalog",
        "catalog_select": base + "/v1/catalog/select",
        "skill": base + "/skill.md",
        "x402": base + "/.well-known/x402",
        "llms": base + "/llms.txt",
        "agents": base + "/AGENTS.md",
        "agent_products": base + "/.well-known/agent-products.json",
        "paid_endpoint": base + "/v1/json/reliable",
        "price_usdc": "0.003",
        "network": "eip155:8453",
        "protocol": "x402",
        "pypi": "agent-json-reliability",
        "mcp_name": "io.github.toninovo4249-ai/agent-json-reliability",
    }


def indexnow_key_body() -> str:
    return INDEXNOW_KEY

