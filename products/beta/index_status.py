"""402 Index per-product ledger. 10 submissions/hour. No duplicate spam."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from products.beta.product_registry import PRODUCTS
from products.beta.settings import ROOT

STATUS_FILE = ROOT / "reports" / "402index_status.json"
STATUSES = ("NOT_SUBMITTED", "SUBMITTED_PENDING", "INDEXED", "REJECTED", "RATE_LIMITED", "PENDING_RETRY")
HOUR = timedelta(hours=1)
BATCH_LIMIT = 10
MAX_WINDOW_WAIT_SECONDS = 30

V185_ACCEPTED = ("json_reliable", "json_contract_check", "web_extract", "web_markdown")
V185_RATE_LIMITED = (
    "json_diff",
    "web_tables",
    "web_metadata",
    "web_link_map",
    "evidence_pack",
    "evidence_compare",
)
V185_LAST_AT = "2026-09-22T13:43:05+00:00"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def empty_products() -> dict[str, dict[str, Any]]:
    return {
        p["id"]: {
            "id": p["id"],
            "path": p["path"],
            "status": "NOT_SUBMITTED",
            "http": None,
            "updated_at": None,
            "note": None,
        }
        for p in PRODUCTS
    }


def seed_v185() -> dict[str, Any]:
    products = empty_products()
    for pid in V185_ACCEPTED:
        products[pid].update({"status": "SUBMITTED_PENDING", "http": 201, "updated_at": V185_LAST_AT, "note": "v185_accepted"})
    for pid in V185_RATE_LIMITED:
        products[pid].update({"status": "RATE_LIMITED", "http": 422, "updated_at": V185_LAST_AT, "note": "probe_got_429_not_402"})
    return {
        "last_submit_at": V185_LAST_AT,
        "submitted_this_hour": 10,
        "products": products,
        "history": [{"at": V185_LAST_AT, "submitted": 10, "accepted": list(V185_ACCEPTED), "rate_limited": list(V185_RATE_LIMITED)}],
    }


def load_status() -> dict[str, Any]:
    if STATUS_FILE.exists():
        try:
            data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and data.get("products"):
            merged = empty_products()
            for pid, row in (data.get("products") or {}).items():
                if pid in merged and isinstance(row, dict):
                    merged[pid].update(row)
            data["products"] = merged
            return data
    return seed_v185()


def save_status(data: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def counts(data: dict[str, Any] | None = None) -> dict[str, int]:
    data = data or load_status()
    products = data.get("products") or {}
    out = {s: 0 for s in STATUSES}
    for row in products.values():
        st = row.get("status") or "NOT_SUBMITTED"
        if st not in out:
            st = "NOT_SUBMITTED"
        out[st] += 1
    return out


def next_submit_at(data: dict[str, Any] | None = None) -> datetime:
    data = data or load_status()
    last = _parse(data.get("last_submit_at"))
    if last is None:
        return _now()
    return last + HOUR


def seconds_until_window(data: dict[str, Any] | None = None) -> float:
    nxt = next_submit_at(data)
    return max(0.0, (nxt - _now()).total_seconds())


def queue_ids(data: dict[str, Any] | None = None, limit: int = BATCH_LIMIT) -> list[str]:
    data = data or load_status()
    products = data.get("products") or {}
    retry = []
    fresh = []
    for p in PRODUCTS:
        row = products.get(p["id"]) or {}
        st = row.get("status") or "NOT_SUBMITTED"
        if st in {"INDEXED", "SUBMITTED_PENDING", "REJECTED"}:
            continue
        if st in {"RATE_LIMITED", "PENDING_RETRY"}:
            retry.append(p["id"])
        else:
            fresh.append(p["id"])
    return (retry + fresh)[: max(0, min(limit, BATCH_LIMIT))]


def mark_result(data: dict[str, Any], product_id: str, http: int | None, body: Any = None) -> None:
    products = data.setdefault("products", empty_products())
    row = products.setdefault(product_id, {"id": product_id, "status": "NOT_SUBMITTED"})
    now = _now().isoformat()
    row["http"] = http
    row["updated_at"] = now
    text = str(body)[:400]
    row["note"] = text
    if http in {200, 201}:
        row["status"] = "SUBMITTED_PENDING"
    elif http == 429:
        row["status"] = "PENDING_RETRY"
        row["retry_at"] = ( _now() + HOUR).isoformat()
    elif http == 422 and ("429" in text or "rate" in text.lower()):
        row["status"] = "PENDING_RETRY"
        row["retry_at"] = (_now() + HOUR).isoformat()
    elif http and http >= 400:
        row["status"] = "REJECTED"
    else:
        row["status"] = "RATE_LIMITED"


def mark_indexed_paths(data: dict[str, Any], listed_paths: set[str]) -> None:
    products = data.get("products") or {}
    for p in PRODUCTS:
        path = p["path"]
        if path in listed_paths or any(path in x for x in listed_paths):
            products[p["id"]]["status"] = "INDEXED"


def mark_pending_retry(data: dict[str, Any], retry_at: datetime, reason: str) -> list[str]:
    """Hourly/rate-limited leftovers. Never sleep for the window."""
    products = data.setdefault("products", empty_products())
    iso = retry_at.isoformat()
    marked = []
    for p in PRODUCTS:
        row = products.get(p["id"]) or {}
        st = row.get("status") or "NOT_SUBMITTED"
        if st in {"INDEXED", "SUBMITTED_PENDING", "REJECTED"}:
            continue
        row["status"] = "PENDING_RETRY"
        row["retry_at"] = iso
        row["note"] = reason
        row["updated_at"] = _now().isoformat()
        products[p["id"]] = row
        marked.append(p["id"])
    data["earliest_retry_at"] = iso
    data["pending_retry_ids"] = marked
    save_status(data)
    return marked


def apply_batch(data: dict[str, Any], submitted_ids: list[str]) -> None:
    data["last_submit_at"] = _now().isoformat()
    data["submitted_this_hour"] = len(submitted_ids)
    hist = data.setdefault("history", [])
    hist.append({"at": data["last_submit_at"], "submitted_ids": submitted_ids})
    save_status(data)
