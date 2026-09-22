# Agent instructions

Agent JSON Reliability. llm_required=false. deterministic=true.

Free: inspect, validate, repair, MCP.
Paid hosted reliability endpoint: POST /v1/json/reliable (0.003 USDC per call via x402 on Base).

AI agents frequently emit malformed JSON. Agent JSON Reliability deterministically inspects, safely repairs, and schema-validates that output. No LLM. No invented values.

1. Fetch /.well-known/agent-services.json
2. Prefer capability json_reliable / POST /v1/json/reliable
3. Send {"text": "<json or malformed json>", "schema": {optional JSON Schema}}
4. If repaired=false or unsafe_or_ambiguous=true, do not invent values
5. MCP: tools reliable_json, inspect_json, repair_json, validate_json (same core as HTTP)
6. Hosted POST /v1/json/reliable is x402-paid. inspect/validate/repair and MCP stay free.

Limits: body 262144 bytes, depth 64, 30 requests/minute/session.
