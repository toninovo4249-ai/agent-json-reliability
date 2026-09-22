from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from products.beta.settings import PAID_LEDGER_PATH


def _conn() -> sqlite3.Connection:
    PAID_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(PAID_LEDGER_PATH))
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS paid_calls (
          id INTEGER PRIMARY KEY,
          timestamp_utc TEXT NOT NULL,
          endpoint TEXT,
          payer TEXT,
          network TEXT,
          asset TEXT,
          price TEXT,
          tx_hash TEXT,
          settlement_status TEXT,
          response_status INTEGER,
          processing_ms REAL
        )
        """
    )
    c.commit()
    return c


def record_paid_call(row: dict[str, Any]) -> None:
    # Never store request JSON payloads.
    c = _conn()
    c.execute(
        """
        INSERT INTO paid_calls (
          timestamp_utc, endpoint, payer, network, asset, price, tx_hash,
          settlement_status, response_status, processing_ms
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            (row.get("endpoint") or "")[:200],
            (row.get("payer") or "")[:128] or None,
            row.get("network"),
            row.get("asset"),
            str(row.get("price") or ""),
            row.get("tx_hash"),
            row.get("settlement_status"),
            int(row.get("response_status") or 0),
            float(row.get("processing_ms") or 0),
        ),
    )
    c.commit()
    c.close()


def paid_metrics() -> dict[str, Any]:
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM paid_calls WHERE settlement_status='settled'").fetchone()[0]
    buyers = [
        r[0]
        for r in c.execute(
            "SELECT payer, COUNT(*) FROM paid_calls WHERE settlement_status='settled' AND payer IS NOT NULL AND payer!='' GROUP BY payer"
        ).fetchall()
    ]
    distinct = len(buyers)
    repeat = sum(1 for _p, cnt in (
        c.execute(
            "SELECT payer, COUNT(*) FROM paid_calls WHERE settlement_status='settled' AND payer IS NOT NULL AND payer!='' GROUP BY payer"
        ).fetchall()
    ) if cnt >= 2)
    # price stored as USDC decimal string; sum settled prices
    rows = c.execute("SELECT price FROM paid_calls WHERE settlement_status='settled'").fetchall()
    revenue = 0.0
    for (p,) in rows:
        try:
            revenue += float(p)
        except (TypeError, ValueError):
            pass
    c.close()
    return {
        "paid_calls": int(n),
        "distinct_paid_buyers": distinct,
        "repeat_paid_buyers": repeat,
        "paid_revenue_usdc": round(revenue, 6),
    }
