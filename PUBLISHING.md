# Publication steps (user-authorized)

Official MCP Registry docs (2025-12-11 schema, preview registry):

- https://modelcontextprotocol.io/registry
- https://modelcontextprotocol.io/registry/package-types
- https://modelcontextprotocol.io/registry/remote-servers
- Publisher CLI: https://github.com/modelcontextprotocol/registry (`mcp-publisher validate` / `login` / `publish`)

GitHub username: `toninovo4249-ai`  
MCP namespace: `io.github.toninovo4249-ai/agent-json-reliability`  
Expected remote: `https://github.com/toninovo4249-ai/agent-json-reliability.git`

## Why stdio/package, not a temporary remote

| option | durability | zero-cost | notes |
|---|---|---|---|
| REMOTE_HTTP_MCP (`POST /mcp`) | depends on a stable HTTPS origin | yes if you already host | Temporary tunnel hostnames change; do not put them in server.json remotes |
| STDIO/PACKAGE_MCP (PyPI + uvx) | durable | PyPI accounts are free | Official registry verifies `mcp-name:` in the package README |

**Recommend: STDIO/PACKAGE_MCP.** Keep remote MCP for live beta testing via `PUBLIC_BASE_URL` only.

Official registry hosts **metadata**, not code. Before `mcp-publisher publish` you need either:

1. A public PyPI package `agent-json-reliability` version `0.1.0` whose README contains `<!-- mcp-name: io.github.toninovo4249-ai/agent-json-reliability -->`, or
2. A durable public remote URL (not a Quick Tunnel), or
3. An MCPB GitHub Release artifact (URL must contain `mcp`, plus `fileSha256`)

Simplest zero-cost route for this Python server: **GitHub public repo + PyPI + stdio**.

## 1. Create the public GitHub repository

From this directory (`release/agent-json-reliability`):

If GitHub CLI is authenticated (you run `gh auth login` yourself if needed):

```bash
gh repo create toninovo4249-ai/agent-json-reliability --public --source=. --remote=origin --push --description "Deterministic JSON repair and JSON Schema validation for AI agents and software. No LLM required."
```

Browser: create an empty public repository named `agent-json-reliability` under `toninovo4249-ai`, then:

```bash
git remote add origin https://github.com/toninovo4249-ai/agent-json-reliability.git
git branch -M main
git push -u origin main
```

Suggested GitHub topics: json, json-schema, json-repair, ai-agents, mcp, fastapi, agent-tools, developer-tools, llm-tools, structured-output

This package does not require a paid GitHub account.

## 2. PyPI (free account, user auth) then Official MCP Registry

PyPI is required for the durable `uvx` / `registryType: pypi` path. Do not upload until you have a free PyPI account and run auth yourself:

```bash
python -m pip install build twine
python -m build
python -m twine upload dist/*
```

Then:

```bash
mcp-publisher validate ./server.json
mcp-publisher login github
mcp-publisher publish ./server.json
```

`login github` opens GitHub device OAuth. Namespace must match `io.github.toninovo4249-ai/agent-json-reliability`.

Do **not** run `mcp-publisher publish` until the GitHub repo exists and PyPI ownership verification can succeed (README `mcp-name` on the published package).

## 3. Demand accounting

Crawlers, directory indexers, and registry verification calls are not real demand. Only unknown external successful product calls count.
