# Security

- Fail closed on oversized or deeply nested JSON, evil regex, remote `$ref`, and header abuse.
- Request bodies are not stored in telemetry (metadata only).
- Repair never invents missing semantic values. Ambiguous input is refused.
- Origin bind defaults to 127.0.0.1. Non-local bind requires `PUBLIC_BETA_CONFIRM=true`.
- Do not open firewall or router ports from this package.
- Temporary HTTPS tunnels (if you start them) are not production hosting and must not be the Official MCP Registry canonical remote.
- Report vulnerabilities privately; do not file public issues with exploit payloads.

Kill switch: stop the process. `PUBLIC_BETA_ENABLED=false`.
