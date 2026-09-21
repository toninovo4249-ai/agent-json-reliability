# Agent JSON Reliability

STATUS=BETA version `0.1.0`

AI agents and software frequently emit malformed JSON: markdown fences, trailing commas, single quotes, `True`/`False`/`None`, and extra prose around one object.

**Agent JSON Reliability** is a deterministic pipeline for that failure mode:

1. **inspect** — diagnose whether the text is JSON and which failures are present
2. **safe repair** — apply only structural, unambiguous fixes
3. **validate** — optional JSON Schema check on the result
4. **structured diagnostics** — `valid_original`, `repaired`, `valid_final`, `schema_valid`, `unsafe_or_ambiguous`, `changes`, `errors`

This is not a generic jsonschema wrapper. The primary value is turning **malformed agent output** into reliable structured data **without an LLM** and **without inventing semantic values**.

When repair would require guessing (truncated objects, missing values, competing JSON documents), the service **refuses**. That is correct behavior.

Primary HTTP endpoint: `POST /v1/json/reliable`

MCP tools (same core functions, no duplicate implementation): `json_reliable` / `reliable_json`, `validate_json`, `repair_json`, `inspect_json`

<!-- mcp-name: io.github.toninovo4249-ai/agent-json-reliability -->

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

## HTTP examples

See `examples/curl.md`, `examples/python.py`, `examples/javascript.js`.

Remote examples use `${PUBLIC_BASE_URL}`. Local default is `http://127.0.0.1:8770`.

Share URLs (optional, unverified telemetry tags):

- `/?source=github`
- `/?source=mcp-registry`
- `/?source=api-directory`

## MCP (stdio — durable)

Package transport does not depend on a temporary public URL.

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

After you publish to PyPI (free): `uvx agent-json-reliability`.

Remote HTTP MCP (`POST /mcp`) is for a running instance. Prefer stdio/package for Official MCP Registry metadata.

## Machine discovery

- `GET /.well-known/agent-services.json`
- `GET /openapi.json`
- `GET /llms.txt`
- `GET /AGENTS.md`
- `POST /mcp` JSON-RPC (`tools/list`, `tools/call`)

## What this package does not include

No Hunter market database, no private reports, no Windows user paths, no collectors, no wallets, no x402 payment.

Free beta: no auth, no payment.
