from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from jsonschema import Draft202012Validator, Draft7Validator, Draft4Validator, Draft201909Validator
from jsonschema.exceptions import SchemaError, ValidationError

from products.common import MAX_DEPTH, MAX_SCHEMA_BYTES, VALIDATE_TIMEOUT_S
from products.common.timing import Clock

_REMOTE_HINTS = ("http://", "https://")


def _depth(obj: Any, limit: int = MAX_DEPTH, n: int = 0) -> int:
    if n > limit:
        return n
    if isinstance(obj, dict):
        if not obj:
            return n
        return max(_depth(v, limit, n + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return n
        return max(_depth(v, limit, n + 1) for v in obj[:32])
    return n


def _schema_has_remote_ref(schema: Any) -> bool:
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.lower().startswith(_REMOTE_HINTS):
            return True
        return any(_schema_has_remote_ref(v) for v in schema.values())
    if isinstance(schema, list):
        return any(_schema_has_remote_ref(v) for v in schema)
    return False


def _schema_pattern_too_evil(schema: Any) -> bool:
    if isinstance(schema, dict):
        pat = schema.get("pattern")
        if isinstance(pat, str) and (len(pat) > 200 or pat.count("+") + pat.count("*") > 12):
            return True
        return any(_schema_pattern_too_evil(v) for v in schema.values())
    if isinstance(schema, list):
        return any(_schema_pattern_too_evil(v) for v in schema)
    return False


def _pick_validator(schema: dict):
    draft = str(schema.get("$schema") or "")
    if "draft-07" in draft or "draft-7" in draft:
        return Draft7Validator
    if "draft-04" in draft:
        return Draft4Validator
    if "2019-09" in draft:
        return Draft201909Validator
    return Draft202012Validator


def _format_error(err: ValidationError) -> dict[str, Any]:
    path = "/" + "/".join(str(p) for p in err.absolute_path)
    spath = "/" + "/".join(str(p) for p in err.absolute_schema_path)
    return {
        "path": path if path != "/" else "/",
        "schema_path": spath,
        "keyword": err.validator,
        "message": err.message[:500],
    }


def _run_validate(instance: Any, schema: dict) -> tuple[bool, list[dict[str, Any]]]:
    Validator = _pick_validator(schema)
    validator = Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return len(errors) == 0, [_format_error(e) for e in errors[:50]]


def validate_json(instance: Any, schema: dict | None) -> dict[str, Any]:
    with Clock() as sw:
        valid_json = True
        schema_valid = None
        errors: list[dict[str, Any]] = []
        ok = True
        try:
            dumped = json.dumps(instance)
        except (TypeError, ValueError):
            valid_json = False
            ok = False
            errors.append({"path": "/", "schema_path": "/", "keyword": "type", "message": "instance is not JSON-serializable"})
            return {
                "ok": False,
                "valid_json": False,
                "schema_valid": False,
                "errors": errors,
                "error_count": len(errors),
                "processing_ms": sw.ms,
            }
        if len(dumped.encode("utf-8")) > 262_144:
            return {
                "ok": False,
                "valid_json": True,
                "schema_valid": False,
                "errors": [{"path": "/", "schema_path": "/", "keyword": "maxSize", "message": "instance exceeds size limit"}],
                "error_count": 1,
                "processing_ms": sw.ms,
            }
        if _depth(instance) > MAX_DEPTH:
            return {
                "ok": False,
                "valid_json": True,
                "schema_valid": False,
                "errors": [{"path": "/", "schema_path": "/", "keyword": "maxDepth", "message": "instance exceeds depth limit"}],
                "error_count": 1,
                "processing_ms": sw.ms,
            }
        if schema is None:
            return {
                "ok": True,
                "valid_json": True,
                "schema_valid": None,
                "errors": [],
                "error_count": 0,
                "processing_ms": sw.ms,
            }
        raw = json.dumps(schema)
        if len(raw.encode("utf-8")) > MAX_SCHEMA_BYTES:
            return {
                "ok": False,
                "valid_json": True,
                "schema_valid": False,
                "errors": [{"path": "/", "schema_path": "/", "keyword": "schemaSize", "message": "schema exceeds size limit"}],
                "error_count": 1,
                "processing_ms": sw.ms,
            }
        if _schema_has_remote_ref(schema):
            return {
                "ok": False,
                "valid_json": True,
                "schema_valid": False,
                "errors": [{"path": "/", "schema_path": "/$ref", "keyword": "remoteRef", "message": "remote $ref is forbidden"}],
                "error_count": 1,
                "processing_ms": sw.ms,
            }
        if _schema_pattern_too_evil(schema):
            return {
                "ok": False,
                "valid_json": True,
                "schema_valid": False,
                "errors": [{"path": "/", "schema_path": "/pattern", "keyword": "pattern", "message": "pathological pattern rejected"}],
                "error_count": 1,
                "processing_ms": sw.ms,
            }
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_run_validate, instance, schema)
                schema_ok, errors = fut.result(timeout=VALIDATE_TIMEOUT_S)
            schema_valid = schema_ok
            ok = schema_ok
        except FuturesTimeout:
            ok = False
            schema_valid = False
            errors = [{"path": "/", "schema_path": "/", "keyword": "timeout", "message": "validation timeout"}]
        except SchemaError as e:
            ok = False
            schema_valid = False
            errors = [{"path": "/", "schema_path": "/", "keyword": "schema", "message": str(e)[:500]}]
        except Exception as e:  # noqa: BLE001 — surface validator failures as errors, never raise to agents
            ok = False
            schema_valid = False
            errors = [{"path": "/", "schema_path": "/", "keyword": "internal", "message": type(e).__name__}]
        return {
            "ok": ok,
            "valid_json": valid_json,
            "schema_valid": schema_valid,
            "errors": errors,
            "error_count": len(errors),
            "processing_ms": sw.ms,
        }
