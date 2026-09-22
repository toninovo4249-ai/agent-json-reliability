"""Counters only. Never store page bodies."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from products.beta.settings import ROOT

DB = Path(ROOT / "data" / "evidence_pack_metrics.sqlite")


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    c.execute(
        """CREATE TABLE IF NOT EXISTS evidence_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
        client_hash TEXT,
        url_count INTEGER,
        success INTEGER,
        fetch_failures INTEGER,
        http_status INTEGER,
        paid INTEGER DEFAULT 0
        )"""
    )
    c.commit()
    return c


def record_pack(*, client_hash: str | None, url_count: int, success: bool, fetch_failures: int, http_status: int, paid: bool = False) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO evidence_events(ts, client_hash, url_count, success, fetch_failures, http_status, paid) VALUES (?,?,?,?,?,?,?)",
        (
            datetime.now(timezone.utc).isoformat(),
            (client_hash or "")[:64],
            int(url_count),
            1 if success else 0,
            int(fetch_failures),
            int(http_status),
            1 if paid else 0,
        ),
    )
    c.commit()
    c.close()


def evidence_metrics() -> dict[str, Any]:
    try:
        c = _conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM evidence_events").fetchall()]
        c.close()
    except Exception:
        rows = []
    by_client: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("success") and r.get("client_hash"):
            by_client[str(r["client_hash"])] += 1
    distinct = len(by_client)
    repeat = sum(1 for n in by_client.values() if n >= 2)
    return {
        "external_calls": len(rows),
        "paid_402_calls": sum(1 for r in rows if r.get("paid")),
        "successful_packs": sum(1 for r in rows if r.get("success")),
        "fetch_failures": sum(int(r.get("fetch_failures") or 0) for r in rows),
        "distinct_buyers": distinct,
        "repeat_buyers": repeat,
        "PAYMENT_ENABLED": False,
    }
