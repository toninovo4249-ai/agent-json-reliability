from __future__ import annotations

from typing import Any

from products.agent_json_reliability.reliable import reliable_json


def reliable_batch(items: list[Any], schema: dict | None = None, max_n: int = 20) -> dict[str, Any]:
    if not isinstance(items, list):
        return {"ok": False, "error_class": "batch_not_list", "results": []}
    if len(items) > max_n:
        return {"ok": False, "error_class": "batch_too_large", "results": [], "max": max_n}
    out = []
    for it in items:
        text = it if isinstance(it, str) else (it or {}).get("text") if isinstance(it, dict) else str(it)
        sch = schema
        if isinstance(it, dict) and it.get("schema") is not None:
            sch = it.get("schema")
        out.append(reliable_json(str(text or ""), sch if isinstance(sch, dict) else None))
    return {"ok": True, "n": len(out), "results": out, "payment_required": False}
