from __future__ import annotations

from html import escape

from products.beta.settings import current_base_url, public_exposure_mode
from products.beta.x402_gate import payment_flags_on

OPENAPI_DESCRIPTION = (
    "Agent JSON Reliability. "
    "Free: inspect, validate, repair, MCP. "
    "Paid hosted reliability endpoint: POST /v1/json/reliable "
    "(0.003 USDC per call via x402 on Base). "
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
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reliable JSON for AI agents</title>
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
     · <a href="/llms.txt">llms.txt</a> · <a href="/AGENTS.md">AGENTS.md</a></p>
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
    base = current_base_url()
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

Limits: body 262144 bytes, depth 64, 30 requests/minute/session.
"""


def llms_txt() -> str:
    base = current_base_url()
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
    )


def robots_txt() -> str:
    return "User-agent: *\nAllow: /\nDisallow: /v16-\n"
