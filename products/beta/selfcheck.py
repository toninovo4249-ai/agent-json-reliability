from __future__ import annotations

from products.agent_json_reliability.inspect import inspect_json
from products.agent_json_reliability.repair import repair_json
from products.agent_json_reliability.reliable import reliable_json
from products.agent_json_reliability.validate import validate_json


def ready_selfcheck() -> dict:
    v = validate_json({"n": 1}, {"type": "object"})
    r = repair_json("{'n': 1}")
    i = inspect_json('{"n":1}')
    rel = reliable_json("{'n': 1}", {"type": "object"})
    ok = bool(v.get("ok") and r.get("repaired") and i.get("valid_json") is False or i.get("valid_json") and rel.get("valid_final"))
    # inspect of valid json
    i2 = inspect_json('{"n":1}')
    ok = bool(v.get("ok")) and bool(r.get("json") == {"n": 1}) and bool(i2.get("valid_json")) and bool(rel.get("schema_valid"))
    return {"ready": ok, "checks": {"validate": v.get("ok"), "repair": r.get("json") == {"n": 1}, "inspect": i2.get("valid_json"), "reliable": rel.get("schema_valid")}}
