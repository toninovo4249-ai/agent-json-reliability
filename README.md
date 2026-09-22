# Agent JSON Reliability

Deterministic JSON repair + JSON Schema validation for AI agents.  
No LLM. Safe refusal on ambiguity.

[![PyPI version](https://img.shields.io/pypi/v/agent-json-reliability.svg)](https://pypi.org/project/agent-json-reliability/)
[![Python](https://img.shields.io/pypi/pyversions/agent-json-reliability.svg)](https://pypi.org/project/agent-json-reliability/)
[![MCP](https://img.shields.io/badge/MCP-stdio%20%2B%20PyPI-555.svg)](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.toninovo4249-ai%2Fagent-json-reliability)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

STATUS=BETA `0.1.0` · [GitHub](https://github.com/toninovo4249-ai/agent-json-reliability) · [PyPI](https://pypi.org/project/agent-json-reliability/) · [Official MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.toninovo4249-ai%2Fagent-json-reliability)

**Problem:** agents emit malformed JSON (fences, trailing commas, single quotes). This tool inspects, safely repairs, and schema-validates that text. No LLM. No invented values.

| Path | Cost |
| --- | --- |
| Local MCP (`uvx agent-json-reliability`) | Free |
| Hosted `POST /v1/json/inspect`, `/validate`, `/repair`, `/mcp` | Free |
| Hosted `POST /v1/json/reliable` | **0.003 USDC** on Base via x402 |

Machine catalog: https://agent-json-reliability.onrender.com/v1/catalog  
Skill: https://agent-json-reliability.onrender.com/skill.md

## Quick start

```bash
uvx agent-json-reliability
```

MCP client config (stdio, published package):

```json
{
  "mcpServers": {
    "agent-json-reliability": {
      "command": "uvx",
      "args": ["agent-json-reliability"]
    }
  }
}
```

<!-- mcp-name: io.github.toninovo4249-ai/agent-json-reliability -->

AI agents and software frequently emit malformed JSON: markdown fences, trailing commas, single quotes, `True`/`False`/`None`, and extra prose around one object.

**Agent JSON Reliability** is a deterministic pipeline for that failure mode:

1. **inspect** — diagnose whether the text is JSON and which failures are present
2. **safe repair** — apply only structural, unambiguous fixes
3. **validate** — optional JSON Schema check on the result
4. **structured diagnostics** — `valid_original`, `repaired`, `valid_final`, `schema_valid`, `unsafe_or_ambiguous`, `changes`, `errors`

This is not a generic jsonschema wrapper. Missing semantic values are never invented. Ambiguous input is refused.

Primary HTTP endpoint (local/self-hosted): `POST /v1/json/reliable`

MCP tools (same core functions): `reliable_json`, `validate_json`, `repair_json`, `inspect_json`

## Before / after (safe repair)

Malformed agent output:

```json
{
  "text": "```json\n{\"name\":\"alice\",\"age\":30,}\n```"
}
```

Expected result (semantically equivalent valid JSON):

- `valid_original=false`
- `repaired=true`
- `valid_final=true`
- `unsafe_or_ambiguous=false`
- `json` → `{"name":"alice","age":30}`

If a schema is supplied and satisfied: `schema_valid=true`.

## Safe refusal (ambiguous)

Truncated input such as `{"user":` is JSON-intended but not deterministically repairable without inventing keys or values.

Expected:

- HTTP `200` (documented safe response)
- `valid_final=false`
- `unsafe_or_ambiguous=true` **or** `repaired=false`

Do not treat a correct refusal as a product failure.

## Run locally (no Hunter)

```bash
python -m pip install -r requirements.txt
python serve.py
```

Binds `127.0.0.1:8770` by default. Set `PUBLIC_BASE_URL` to an HTTPS origin only when you expose the process yourself. Do not commit a temporary tunnel hostname as the canonical URL.

## Hosted API (x402)

Public origin: `https://agent-json-reliability.onrender.com`

Inspect / validate / repair / MCP stay free. `POST /v1/json/reliable` returns HTTP 402 until an x402 `PAYMENT-SIGNATURE` settles **3000 atomic USDC (0.003)** on Base (`eip155:8453`) via PayAI.

```bash
curl -s -D - -o /tmp/ajr.json -X POST https://agent-json-reliability.onrender.com/v1/json/reliable \
  -H "content-type: application/json" \
  -d '{"text":"{'\''a'\'': 1}"}'
# Expect: HTTP/1.1 402  and a PAYMENT-REQUIRED header. Do not send a signature unless you intend to pay.
```

## HTTP examples

See `examples/curl.md`, `examples/python.py`, `examples/javascript.js`.

Remote examples use `https://agent-json-reliability.onrender.com`. Local default is `http://127.0.0.1:8770`.

Share URLs (optional, unverified telemetry tags):

- `/?source=github`
- `/?source=mcp-registry`
- `/?source=api-directory`

## MCP (stdio — durable)

Package transport does not depend on a temporary public URL. Prefer `uvx` (above). From a checkout:

```json
{
  "mcpServers": {
    "agent-json-reliability": {
      "command": "python",
      "args": ["-m", "products.gateway.mcp_stdio"]
    }
  }
}
```

Remote HTTP MCP (`POST /mcp`) is for a running instance.

## Machine discovery

- Hosted origin: https://agent-json-reliability.onrender.com
- `GET /.well-known/agent-services.json`
- `GET /.well-known/agent.json`
- `GET /.well-known/x402`
- `GET /openapi.json`
- `GET /llms.txt` · `GET /llms-full.txt` · `GET /AGENTS.md` · `GET /sitemap.xml` · `GET /robots.txt`
- `POST /mcp` JSON-RPC (`tools/list`, `tools/call`)

## What this package does not include

No Hunter market database, no private reports, no Windows user paths, no collectors, no wallets in this package. Hosted `/v1/json/reliable` is x402-paid; local MCP and inspect/validate/repair are free.
