from __future__ import annotations

from typing import Any


def walk_limits(obj: Any, *, max_depth: int, max_nodes: int, max_arr: int, max_keys: int, max_str: int) -> str | None:
    """Return error_class or None. Fail closed on bombs."""
    nodes = 0

    def rec(v: Any, d: int) -> str | None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            return "too_many_nodes"
        if d > max_depth:
            return "max_depth"
        if isinstance(v, str) and len(v) > max_str:
            return "string_too_long"
        if isinstance(v, list):
            if len(v) > max_arr:
                return "array_too_large"
            for item in v:
                err = rec(item, d + 1)
                if err:
                    return err
        elif isinstance(v, dict):
            if len(v) > max_keys:
                return "object_too_large"
            for k, val in v.items():
                if isinstance(k, str) and len(k) > max_str:
                    return "string_too_long"
                err = rec(val, d + 1)
                if err:
                    return err
        return None

    return rec(obj, 0)


def _schema_flags(schema: Any, depth: int = 0) -> str | None:
    if depth > 64:
        return "schema_max_depth"
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str):
            low = ref.lower()
            if low.startswith("http://") or low.startswith("https://"):
                return "remote_ref"
            if ref.strip() in {"#", "#/"}:
                return "recursive_schema"
        pat = schema.get("pattern")
        if isinstance(pat, str) and (len(pat) > 200 or pat.count("+") + pat.count("*") > 12 or "(a+" in pat or ")+)" in pat):
            return "evil_pattern"
        for v in schema.values():
            err = _schema_flags(v, depth + 1)
            if err:
                return err
    elif isinstance(schema, list):
        for v in schema:
            err = _schema_flags(v, depth + 1)
            if err:
                return err
    return None


def schema_limits(schema: Any, *, max_depth: int) -> str | None:
    if schema is None:
        return None
    if not isinstance(schema, dict):
        return "invalid_schema"
    flagged = _schema_flags(schema)
    if flagged:
        return flagged
    err = walk_limits(schema, max_depth=max_depth, max_nodes=5000, max_arr=500, max_keys=500, max_str=2000)
    if err:
        return "schema_" + err
    return None
