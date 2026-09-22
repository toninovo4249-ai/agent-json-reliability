from __future__ import annotations

from typing import Any

from products.agent_json_reliability.inspect import inspect_json
from products.agent_json_reliability.repair import repair_json
from products.agent_json_reliability.reliable import reliable_json
from products.agent_json_reliability.validate import validate_json
from products.gateway.manifest import tools

JSON_TOOL_NAMES = ("validate_json", "repair_json", "inspect_json", "reliable_json")
EMPTY_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def mcp_tools() -> list[dict[str, Any]]:
    out = []
    for t in tools():
        name = t["tool_name"]
        if name not in JSON_TOOL_NAMES:
            continue
        out.append({"name": name, "description": t["description"], "inputSchema": t["input_schema"]})
    return out


def mcp_server_card() -> dict[str, Any]:
    return {
        "serverInfo": {"name": "agent-json-reliability", "version": "0.1.0"},
        "authentication": {"required": False, "schemes": []},
        "configSchema": EMPTY_CONFIG_SCHEMA,
        "tools": mcp_tools(),
        "resources": [],
        "prompts": [],
    }


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    if name == "validate_json":
        return validate_json(args.get("instance"), args.get("schema"))
    if name == "repair_json":
        return repair_json(str(args.get("text") or ""), args.get("mode") or "safe")
    if name == "inspect_json":
        return inspect_json(str(args.get("text") or ""))
    if name == "reliable_json":
        return reliable_json(str(args.get("text") or ""), args.get("schema"))
    raise ValueError(f"unknown_tool:{name}")


def handle_rpc(body: dict[str, Any]) -> dict[str, Any]:
    method = body.get("method")
    _id = body.get("id")
    params = body.get("params") or {}
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": _id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "agent-json-reliability", "version": "0.1.0"},
            },
        }
    if method in {"notifications/initialized", "initialized"}:
        return {"jsonrpc": "2.0", "id": _id, "result": {}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": _id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": _id, "result": {"tools": mcp_tools()}}
    if method == "tools/call":
        name = params.get("name")
        try:
            result = call_tool(name, params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": _id, "result": {"content": [{"type": "json", "json": result}], "isError": False}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": _id, "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}}
    return {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": "method not found"}}
