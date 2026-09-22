from __future__ import annotations

from fastapi.testclient import TestClient

from products.agent_json_reliability.reliable import reliable_json
from products.beta.app import create_json_beta_app
from products.gateway.mcp_server import call_tool, handle_rpc

POSITIVE = "```json\n{\"name\":\"alice\",\"age\":30,}\n```"
SCHEMA = {"type": "object", "required": ["name", "age"]}
REFUSAL = '{"user":'


def test_local_http_mcp_parity():
    local = reliable_json(POSITIVE, SCHEMA)
    assert local["valid_original"] is False
    assert local["repaired"] is True
    assert local["valid_final"] is True
    client = TestClient(create_json_beta_app())
    http = client.post("/v1/json/reliable", json={"text": POSITIVE, "schema": SCHEMA}).json()
    mcp = call_tool("reliable_json", {"text": POSITIVE, "schema": SCHEMA})
    for k in ("valid_original", "repaired", "valid_final", "schema_valid", "unsafe_or_ambiguous"):
        assert local[k] == http[k] == mcp[k]
    listed = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {"validate_json", "repair_json", "inspect_json", "reliable_json"}
    card = client.get("/.well-known/mcp/server-card.json").json()
    assert card["authentication"]["required"] is False
    assert card["configSchema"] == {"type": "object", "properties": {}, "additionalProperties": False}
    assert {t["name"] for t in card["tools"]} == names
    ref = reliable_json(REFUSAL, None)
    assert ref["valid_final"] is False
    assert ref["unsafe_or_ambiguous"] is True or ref["repaired"] is False
