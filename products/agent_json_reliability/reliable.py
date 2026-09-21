from __future__ import annotations

from typing import Any

from products.agent_json_reliability.inspect import inspect_json
from products.agent_json_reliability.repair import repair_json
from products.agent_json_reliability.validate import validate_json
from products.common.timing import Clock


def reliable_json(text: str, schema: dict | None = None, mode: str = "safe") -> dict[str, Any]:
    """inspect → safe repair if needed → optional schema validate. Same primitives as HTTP tools."""
    with Clock() as sw:
        insp = inspect_json(text)
        valid_original = bool(insp.get("valid_json"))
        changes: list[str] = []
        repaired = False
        payload: Any = None
        unsafe = False
        if valid_original:
            import json

            payload = json.loads(text.strip().lstrip("\ufeff"))
        else:
            rep = repair_json(text, mode)
            repaired = bool(rep.get("repaired"))
            payload = rep.get("json")
            changes = list(rep.get("changes") or [])
            unsafe = bool(rep.get("unsafe_or_ambiguous"))
        valid_final = payload is not None
        schema_valid = None
        errors: list = []
        if valid_final and schema is not None:
            v = validate_json(payload, schema)
            schema_valid = v.get("schema_valid")
            errors = v.get("errors") or []
            valid_final = bool(schema_valid)
        elif not valid_final:
            errors = [{"message": "unrepaired_or_invalid"}]
        return {
            "valid_original": valid_original,
            "repaired": repaired,
            "json": payload,
            "valid_final": valid_final and payload is not None and (schema_valid is not False),
            "schema_valid": schema_valid,
            "unsafe_or_ambiguous": unsafe,
            "changes": changes,
            "errors": errors,
            "inspect": insp,
            "processing_ms": sw.ms,
            "outcome_class": _outcome(valid_original, repaired, payload, schema_valid, errors),
        }


def _outcome(valid_original, repaired, payload, schema_valid, errors) -> str:
    if schema_valid is False:
        return "SCHEMA_INVALID"
    if schema_valid is True:
        return "SCHEMA_VALID"
    if valid_original:
        return "ORIGINAL_VALID"
    if repaired and payload is not None:
        return "SAFE_REPAIR_SUCCESS"
    if any((e.get("message") or "").startswith("schema") for e in errors or []):
        return "INVALID_SCHEMA"
    return "SAFE_REPAIR_REFUSED"
