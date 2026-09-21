from __future__ import annotations

import json
import re
from typing import Any

from products.agent_json_reliability.repair import repair_json
from products.common.timing import Clock

_FAILURES = [
    ("markdown_fence", re.compile(r"```")),
    ("trailing_comma", re.compile(r",\s*[}\]]")),
    ("single_quotes", re.compile(r"'")),
    ("python_literals", re.compile(r"\b(True|False|None)\b")),
    ("comments", re.compile(r"//|/\*")),
    ("leading_prose", None),
    ("truncated", None),
]


def inspect_json(text: str) -> dict[str, Any]:
    with Clock() as sw:
        if not isinstance(text, str):
            text = str(text)
        raw = text.strip()
        valid = False
        err_pos = None
        try:
            json.loads(raw)
            valid = True
        except json.JSONDecodeError as e:
            err_pos = e.pos
        types: list[str] = []
        if re.search(r"```", raw):
            types.append("markdown_fence")
        if re.search(r",\s*[}\]]", raw):
            types.append("trailing_comma")
        if "'" in raw and '"' not in raw:
            types.append("single_quotes")
        if re.search(r"\b(True|False|None)\b", raw):
            types.append("python_literals")
        if "//" in raw or "/*" in raw:
            types.append("comments")
        stripped = raw.lstrip()
        if stripped and stripped[0] not in "{[":
            types.append("leading_prose")
        if raw.count("{") > raw.count("}") or raw.count("[") > raw.count("]"):
            types.append("truncated")
        if re.search(r"\}\s*\{", raw):
            types.append("multiple_objects")
        likely = valid or bool(re.search(r"[\{\[]", raw))
        rep = repair_json(raw)
        complexity = min(100, raw.count("{") + raw.count("[") + raw.count(":") + len(raw) // 200)
        return {
            "valid_json": valid,
            "likely_json": likely,
            "error_position": err_pos,
            "detected_failure_types": types,
            "repair_possible": bool(rep.get("repaired") or valid),
            "estimated_complexity": complexity,
            "processing_ms": sw.ms,
        }
