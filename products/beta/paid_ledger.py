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
          pay_to TEXT,
          network TEXT,
          asset TEXT,
          price TEXT,
          usd_price TEXT,
          amount_atomic TEXT,
          tx_hash TEXT,
          payment_hash TEXT,
          nonce TEXT,
          verify_status TEXT,
          settlement_status TEXT,
          response_status INTEGER,
          processing_ms REAL,
          is_real INTEGER DEFAULT 0
        )
        """
    )
    cols = {r[1] for r in c.execute("PRAGMA table_info(paid_calls)")}
    for name, typ in (("pay_to", "TEXT"), ("verify_status", "TEXT"), ("usd_price", "TEXT")):
        if name not in cols:
            c.execute(f"ALTER TABLE paid_calls ADD COLUMN {name} {typ}")
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


def ledger_writable() -> bool:
    try:
        c = _conn()
        c.execute("SELECT 1 FROM paid_calls LIMIT 1")
        c.close()
        return True
    except Exception:
        return False


def record_paid_call(row: dict[str, Any]) -> None:
    c = _conn()
    price = str(row.get("price") or row.get("usd_price") or "")
    try:
        c.execute(
            """
            INSERT INTO paid_calls (
              timestamp_utc, endpoint, payer, pay_to, network, asset, price, usd_price, amount_atomic,
              tx_hash, payment_hash, nonce, verify_status, settlement_status, response_status, processing_ms, is_real
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                (row.get("endpoint") or "")[:200],
                (row.get("payer") or None),
                row.get("payTo") or row.get("pay_to"),
                row.get("network"),
                row.get("asset"),
                price,
                str(row.get("usd_price") or price),
                row.get("amount_atomic") or row.get("amount"),
                row.get("tx_hash"),
                row.get("payment_hash"),
                row.get("nonce"),
                row.get("verify_status"),
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


def paid_metrics(endpoint: str | None = None) -> dict[str, Any]:
    c = _conn()
    where = "settlement_status='settled' AND is_real=1"
    args: list[Any] = []
    if endpoint:
        where += " AND endpoint=?"
        args.append(endpoint)
    n = c.execute(f"SELECT COUNT(*) FROM paid_calls WHERE {where}", args).fetchone()[0]
    grouped = c.execute(
        f"SELECT payer, COUNT(*) FROM paid_calls WHERE {where} AND payer IS NOT NULL AND payer!='' GROUP BY payer",
        args,
    ).fetchall()
    distinct = len(grouped)
    repeat = sum(1 for _p, cnt in grouped if cnt >= 2)
    rows = c.execute(
        f"SELECT COALESCE(usd_price, price), amount_atomic FROM paid_calls WHERE {where}",
        args,
    ).fetchall()
    revenue = 0.0
    for p, atomic in rows:
        try:
            revenue += float(p)
        except (TypeError, ValueError):
            try:
                revenue += int(atomic or 0) / 1_000_000
            except (TypeError, ValueError):
                pass
    c.close()
    return {
        "paid_calls": int(n),
        "distinct_paid_buyers": distinct,
        "repeat_paid_buyers": repeat,
        "paid_revenue_usdc": round(revenue, 6),
        "REAL_PAID_CALLS": int(n),
        "DISTINCT_REAL_PAID_BUYERS": distinct,
        "REPEAT_REAL_PAID_BUYERS": repeat,
        "REAL_REVENUE_USDC": round(revenue, 6),
    }


def split_paid_metrics() -> dict[str, Any]:
    total = paid_metrics()
    ajr = paid_metrics("/v1/json/reliable")
    ev = paid_metrics("/v1/evidence/pack")
    return {
        **total,
        "AJR_REAL_PAID_CALLS": ajr["REAL_PAID_CALLS"],
        "AJR_REAL_REVENUE_USDC": ajr["REAL_REVENUE_USDC"],
        "AJR_DISTINCT_PAID_BUYERS": ajr["DISTINCT_REAL_PAID_BUYERS"],
        "EVIDENCE_REAL_PAID_CALLS": ev["REAL_PAID_CALLS"],
        "EVIDENCE_DISTINCT_PAID_BUYERS": ev["DISTINCT_REAL_PAID_BUYERS"],
        "EVIDENCE_REPEAT_PAID_BUYERS": ev["REPEAT_REAL_PAID_BUYERS"],
        "EVIDENCE_REAL_REVENUE_USDC": ev["REAL_REVENUE_USDC"],
        "TOTAL_REAL_PAID_CALLS": total["REAL_PAID_CALLS"],
        "TOTAL_REAL_REVENUE_USDC": total["REAL_REVENUE_USDC"],
    }
