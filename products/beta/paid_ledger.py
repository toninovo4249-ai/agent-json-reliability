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
          amount_atomic TEXT,
          tx_hash TEXT,
          payment_hash TEXT,
          nonce TEXT,
          settlement_status TEXT,
          response_status INTEGER,
          processing_ms REAL,
          is_real INTEGER DEFAULT 0
        )
        """
    )
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS paid_calls_payment_hash ON paid_calls(payment_hash) WHERE payment_hash IS NOT NULL")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS paid_calls_nonce ON paid_calls(nonce) WHERE nonce IS NOT NULL AND nonce!=''")
    c.commit()
    return c


def seen_payment(payment_hash: str | None, nonce: str | None) -> bool:
    c = _conn()
    if payment_hash:
        row = c.execute("SELECT 1 FROM paid_calls WHERE payment_hash=?", (payment_hash,)).fetchone()
        if row:
            c.close()
            return True
    if nonce:
        row = c.execute("SELECT 1 FROM paid_calls WHERE nonce=?", (nonce,)).fetchone()
        if row:
            c.close()
            return True
    c.close()
    return False


def record_paid_call(row: dict[str, Any]) -> None:
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO paid_calls (
              timestamp_utc, endpoint, payer, network, asset, price, amount_atomic,
              tx_hash, payment_hash, nonce, settlement_status, response_status, processing_ms, is_real
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                (row.get("endpoint") or "")[:200],
                (row.get("payer") or None),
                row.get("network"),
                row.get("asset"),
                str(row.get("price") or ""),
                row.get("amount_atomic") or row.get("amount"),
                row.get("tx_hash"),
                row.get("payment_hash"),
                row.get("nonce"),
                row.get("settlement_status"),
                int(row.get("response_status") or 0),
                float(row.get("processing_ms") or 0),
                1 if row.get("is_real") else 0,
            ),
        )
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback()
    finally:
        c.close()


def paid_metrics() -> dict[str, Any]:
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM paid_calls WHERE settlement_status='settled' AND is_real=1").fetchone()[0]
    grouped = c.execute(
        "SELECT payer, COUNT(*) FROM paid_calls WHERE settlement_status='settled' AND is_real=1 AND payer IS NOT NULL AND payer!='' GROUP BY payer"
    ).fetchall()
    distinct = len(grouped)
    repeat = sum(1 for _p, cnt in grouped if cnt >= 2)
    rows = c.execute("SELECT price FROM paid_calls WHERE settlement_status='settled' AND is_real=1").fetchall()
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
