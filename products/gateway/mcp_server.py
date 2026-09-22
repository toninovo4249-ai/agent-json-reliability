from __future__ import annotations

from typing import Any

from products.agent_json_reliability.inspect import inspect_json
from products.agent_json_reliability.repair import repair_json
from products.agent_json_reliability.reliable import reliable_json
from products.agent_json_reliability.validate import validate_json
from products.gateway.manifest import tools


JSON_TOOL_NAMES = ("validate_json", "repair_json", "inspect_json", "reliable_json")
DISCOVERY_TOOL_NAMES = ("list_paid_products", "select_paid_product")


def mcp_tools() -> list[dict[str, Any]]:
    out = []
    for t in tools():
        out.append(
            {
                "name": t["tool_name"],
                "description": t["description"],
                "inputSchema": t["input_schema"],
            }
        )
    out.append(
        {
            "name": "list_paid_products",
            "description": "List 24 paid HTTP x402 products (id, endpoint, price, purpose). Does not execute paid work.",
            "inputSchema": {"type": "object", "properties": {}},
        }
    )
    out.append(
        {
            "name": "select_paid_product",
            "description": "Deterministic router: given a task, return top paid products with endpoint, price, and input example. Does not execute paid work.",
            "inputSchema": {"type": "object", "required": ["task"], "properties": {"task": {"type": "string"}}},
        }
    )
    return out


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    if name == "validate_json":
        return validate_json(args.get("instance"), args.get("schema"))
    if name == "repair_json":
        return repair_json(str(args.get("text") or ""), args.get("mode") or "safe")
    if name == "inspect_json":
        return inspect_json(str(args.get("text") or ""))
    if name == "extract_web_content":
        from products.html_clean_extraction.modes import extract_with_mode

        return extract_with_mode(args.get("html"), args.get("url"), args.get("mode") or "markdown", bool(args.get("allow_fetch")))
    if name == "reliable_json":
        return reliable_json(str(args.get("text") or ""), args.get("schema"))
    if name == "list_paid_products":
        from products.beta.store_catalog import catalog_item
        from products.beta.product_registry import PRODUCTS

        return {
            "paid_work_executed": False,
            "product_count": len(PRODUCTS),
            "products": [
                {
                    "product_id": p["id"],
                    "endpoint": p["path"],
                    "method": "POST",
                    "price_usdc": p["price_usdc"],
                    "purpose": p["purpose"],
                    "category": p["category"],
                }
                for p in PRODUCTS
            ],
        }
    if name == "select_paid_product":
        from products.beta.store_catalog import select_products

        out = select_products(str(args.get("task") or ""))
        out["paid_work_executed"] = False
        return out
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
