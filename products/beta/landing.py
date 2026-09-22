from __future__ import annotations

from html import escape

from products.beta.settings import current_base_url, discovery_server_url, public_exposure_mode
from products.beta.x402_gate import payment_flags_on

INDEXNOW_KEY = "8f2c1a9e4b774d1e9c6a0b3d5e7f1021"

OPENAPI_DESCRIPTION = (
    "Agent JSON Reliability. "
    "Free: inspect, validate, repair, MCP. "
    "Paid x402 endpoints: POST /v1/json/reliable (0.003 USDC) and "
    "POST /v1/evidence/pack (0.0075 USDC Fresh Web Evidence Pack). "
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
  <p>Manifest: <a href="/.well-known/agent-services.json">/.well-known/agent-services.json</a>
     · OpenAPI: <a href="/openapi.json">/openapi.json</a>
     · <a href="/llms.txt">llms.txt</a> · <a href="/AGENTS.md">AGENTS.md</a>
     · <a href="/sitemap.xml">sitemap.xml</a>
     · <a href="/.well-known/agent.json">/.well-known/agent.json</a>
     · <a href="/.well-known/x402">/.well-known/x402</a></p>
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


def agents_md() -> str:
    base = discovery_server_url()
    paid = payment_flags_on()
    pay_note = (
        "POST /v1/json/reliable is paid x402 exact 0.003 USDC on Base. inspect/validate/repair and MCP stay free."
        if paid
        else "Hosted payment flags are off: HTTP routes are free."
    )
    return f"""# Agent instructions

Agent JSON Reliability. llm_required=false. deterministic=true.

Free: inspect, validate, repair, MCP.
Paid hosted reliability endpoint: POST {base}/v1/json/reliable (0.003 USDC per call via x402 on Base when payment is enabled).

AI agents frequently emit malformed JSON. This API deterministically inspects, repairs and schema-validates JSON without another LLM call.

1. GET {base}/.well-known/agent-services.json
2. Prefer capability json_reliable / POST {base}/v1/json/reliable
3. Send {{"text": "<json or malformed json>", "schema": {{optional JSON Schema}}}}
4. Do not invent values if repaired=false
5. {pay_note}
6. Machine discovery: {base}/openapi.json {base}/.well-known/x402 {base}/.well-known/agent.json {base}/sitemap.xml {base}/llms.txt

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
        "AI agents frequently emit malformed JSON. This API deterministically inspects, "
        "repairs and schema-validates JSON without another LLM call.\n"
        f"Primary: POST {base}/v1/json/reliable\n"
        "Capability: json_reliable\n"
        f"deterministic=true llm_required=false mixed_pricing={str(paid).lower()}\n"
        f"Catalog: {base}/.well-known/agent-services.json\n"
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
        "# Paid HTTP\n"
        "POST /v1/json/reliable HTTP 402 then PAYMENT-SIGNATURE x402 exact 0.003 USDC Base USDC\n"
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
        "paid_endpoint": base + "/v1/json/reliable",
        "price_usdc": "0.003",
        "network": "eip155:8453",
        "protocol": "x402",
        "pypi": "agent-json-reliability",
        "mcp_name": "io.github.toninovo4249-ai/agent-json-reliability",
    }


def indexnow_key_body() -> str:
    return INDEXNOW_KEY

