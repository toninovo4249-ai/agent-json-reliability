from __future__ import annotations

import ast
import json
import re
from typing import Any

from products.common.timing import Clock

_FENCE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)```", re.MULTILINE)
_TRAIL_COMMA = re.compile(r",(\s*[}\]])")
_COMMENT_LINE = re.compile(r"(^|[^:])//.*?$", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*[\s\S]*?\*/")


def _extract_fenced(text: str, changes: list[str]) -> str:
    m = _FENCE.search(text)
    if m:
        changes.append("strip_markdown_fence")
        return m.group(1).strip()
    return text


def _extract_balanced(text: str, changes: list[str]) -> str:
    starts = [i for i, ch in enumerate(text) if ch in "{["]
    if not starts:
        return text.strip()
    first = starts[0]
    chunk = text[first:]
    if first > 0 and text[:first].strip():
        changes.append("strip_leading_prose")
    depth_obj = depth_arr = 0
    in_str = False
    esc = False
    last = -1
    for i, ch in enumerate(chunk):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth_obj += 1
        elif ch == "}":
            depth_obj -= 1
        elif ch == "[":
            depth_arr += 1
        elif ch == "]":
            depth_arr -= 1
        if depth_obj == 0 and depth_arr == 0 and ch in "}]":
            last = i
            break
    if last >= 0:
        tail = chunk[last + 1 :]
        st = tail.strip()
        if st.startswith("{") or st.startswith("["):
            changes.append("multiple_json_values")
            return chunk
        if st:
            changes.append("strip_trailing_prose")
        return chunk[: last + 1]
    return chunk


def _strip_comments(text: str, changes: list[str]) -> str:
    if "//" not in text and "/*" not in text:
        return text
    nxt = _COMMENT_BLOCK.sub("", text)
    nxt = _COMMENT_LINE.sub(lambda m: m.group(1), nxt)
    if nxt != text:
        changes.append("strip_comments")
    return nxt


def _py_literals(text: str, changes: list[str]) -> str:
    nxt = re.sub(r"\bTrue\b", "true", text)
    nxt = re.sub(r"\bFalse\b", "false", nxt)
    nxt = re.sub(r"\bNone\b", "null", nxt)
    if nxt != text:
        changes.append("python_literals")
    return nxt


def _trailing_commas(text: str, changes: list[str]) -> str:
    nxt, n = _TRAIL_COMMA.subn(r"\1", text)
    if n:
        changes.append("strip_trailing_commas")
    return nxt


def _close_truncated(text: str, changes: list[str]) -> str | None:
    """Close extra { [ only when the remainder is empty of required values."""
    in_str = False
    esc = False
    stack: list[str] = []
    last_sig = ""
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            last_sig = '"'
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
            last_sig = ch
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()
            last_sig = ch
        elif ch == ":":
            last_sig = ":"
        elif ch == ",":
            last_sig = ","
        elif not ch.isspace():
            last_sig = "v"
    if in_str:
        return None
    if not stack:
        return None
    if last_sig in {":"}:
        return None  # would invent a value
    closed = text + "".join(reversed(stack))
    changes.append("close_truncated_brackets")
    return closed


def _try_load(text: str) -> Any:
    return json.loads(text)


def _literal_eval_jsonish(text: str) -> Any | None:
    try:
        val = ast.literal_eval(text)
    except (SyntaxError, ValueError, MemoryError):
        return None
    if isinstance(val, (dict, list, str, int, float, bool)) or val is None:
        return val
    return None


def repair_json(text: str, mode: str = "safe") -> dict[str, Any]:
    with Clock() as sw:
        changes: list[str] = []
        if not isinstance(text, str):
            return _fail(sw, "text_not_string", changes)
        if len(text.encode("utf-8")) > 262_144:
            return _fail(sw, "too_large", changes)
        raw = text.strip().lstrip("\ufeff")
        if raw != text.strip() or text[:1] == "\ufeff" or text != text.strip():
            changes.append("strip_bom_or_whitespace")
        if not raw:
            return _fail(sw, "empty", changes)

        try:
            parsed = _try_load(raw)
            return _ok(parsed, bool(changes), changes, "high", False, sw)
        except json.JSONDecodeError:
            pass

        work = _extract_fenced(raw, changes)
        work = _extract_balanced(work, changes)
        if "multiple_json_values" in changes:
            return _fail(sw, "multiple_json_values", changes, unsafe=True)
        work = _strip_comments(work, changes)

        looks_py = ("True" in work or "False" in work or "None" in work or ("'" in work and '"' not in work))
        if looks_py:
            lit = _literal_eval_jsonish(work)
            if lit is not None:
                changes.append("python_literal_eval")
                return _ok(lit, True, changes, "medium", False, sw)

        work = _py_literals(work, changes)
        work = _trailing_commas(work, changes)

        try:
            parsed = _try_load(work)
            return _ok(parsed, True, changes, "high", False, sw)
        except json.JSONDecodeError:
            pass

        closed = _close_truncated(work, changes)
        if closed is not None:
            closed = _trailing_commas(closed, changes)
            try:
                parsed = _try_load(closed)
                return _ok(parsed, True, changes, "medium", False, sw)
            except json.JSONDecodeError:
                changes[:] = [c for c in changes if c != "close_truncated_brackets"]

        decoder = json.JSONDecoder()
        try:
            first, idx = decoder.raw_decode(work)
            rest = work[idx:].strip()
            if rest:
                return _fail(sw, "multiple_json_values", changes, unsafe=True)
            return _ok(first, True, changes, "medium", False, sw)
        except json.JSONDecodeError:
            pass

        return _fail(sw, "unambiguous_repair_impossible", changes, unsafe=True)


def _ok(parsed, repaired, changes, confidence, unsafe, sw):
    return {
        "repaired": repaired,
        "json": parsed,
        "changes": changes,
        "confidence": confidence,
        "unsafe_or_ambiguous": unsafe,
        "processing_ms": sw.ms,
    }


def _fail(sw, reason: str, changes: list[str], unsafe: bool = False):
    return {
        "repaired": False,
        "json": None,
        "changes": changes + [reason],
        "confidence": "low",
        "unsafe_or_ambiguous": True if unsafe else False,
        "processing_ms": sw.ms,
    }
