"""Report conflicting structured claims. Do not pick a winner."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def find_contradictions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for c in claims:
        by_key[c["key"]][c["value"]].append(c)
    out: list[dict[str, Any]] = []
    for key, values in sorted(by_key.items()):
        if len(values) < 2:
            continue
        sides = []
        for val, rows in sorted(values.items()):
            sides.append(
                {
                    "value": val,
                    "source_indexes": [r["source_index"] for r in rows],
                    "source_urls": [r["source_url"] for r in rows],
                }
            )
        out.append({"claim": key, "values": sides, "winner": None, "note": "conflicting structured claims; no winner chosen"})
    return out
