"""Local HTTP example. Set PUBLIC_BASE_URL for a remote origin."""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("PUBLIC_BASE_URL") or "http://127.0.0.1:8770"
POSITIVE = {
    "text": "```json\n{\"name\":\"alice\",\"age\":30,}\n```",
    "schema": {"type": "object", "required": ["name", "age"]},
}
REFUSAL = {"text": '{"user":'}


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


if __name__ == "__main__":
    pos = post("/v1/json/reliable", POSITIVE)
    ref = post("/v1/json/reliable", REFUSAL)
    print("positive", pos.get("valid_final"), pos.get("json"))
    print("refusal", ref.get("valid_final"), ref.get("unsafe_or_ambiguous"), ref.get("repaired"))
