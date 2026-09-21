from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from products.beta.settings import DB_PATH, TOOL_PATHS


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY,
          timestamp_utc TEXT,
          ts REAL,
          request_id TEXT,
          endpoint TEXT,
          success INTEGER,
          http_status INTEGER,
          latency_ms REAL,
          request_size_bytes INTEGER,
          response_size_bytes INTEGER,
          error_class TEXT,
          client_type TEXT,
          classification_confidence REAL,
          anonymous_client_hash TEXT,
          repeat_client INTEGER,
          discovery_path TEXT,
          self_reported_source TEXT,
          traffic_kind TEXT,
          outcome_class TEXT,
          beta_version TEXT,
          meaningful INTEGER,
          probe_class TEXT
        );
        CREATE TABLE IF NOT EXISTS free_beta_daily_metrics (
          id INTEGER PRIMARY KEY,
          date_utc TEXT,
          snapshot_utc TEXT,
          metrics_json TEXT
        );
        CREATE TABLE IF NOT EXISTS first_external_use (
          id INTEGER PRIMARY KEY,
          timestamp_utc TEXT,
          endpoint TEXT,
          latency_ms REAL,
          success INTEGER,
          self_reported_source TEXT
        );
        """
    )
    cols = {r[1] for r in c.execute("PRAGMA table_info(events)").fetchall()}
    if "meaningful" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN meaningful INTEGER")
    if "probe_class" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN probe_class TEXT")
    c.commit()
    return c


def record_v16(ev: dict[str, Any]) -> None:
    c = _conn()
    h = ev.get("anonymous_client_hash")
    kind = ev.get("traffic_kind") or "REAL_EXTERNAL_UNKNOWN"
    ep = ev.get("endpoint") or ""
    success = bool(ev.get("success"))
    size = int(ev.get("request_size_bytes") or 0)
    product_call = ep in TOOL_PATHS or (ep == "/mcp" and ev.get("mcp_product_call"))
    meaningful = 1 if (
        kind == "REAL_EXTERNAL_UNKNOWN"
        and product_call
        and success
        and size >= 8
    ) else 0
    if ev.get("meaningful") is not None:
        meaningful = 1 if ev.get("meaningful") else 0
    seen = None
    if h and meaningful:
        seen = c.execute(
            "SELECT 1 FROM events WHERE anonymous_client_hash=? AND meaningful=1 LIMIT 1",
            (h,),
        ).fetchone()
    now = time.time()
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    c.execute(
        """INSERT INTO events(timestamp_utc,ts,request_id,endpoint,success,http_status,latency_ms,
           request_size_bytes,response_size_bytes,error_class,client_type,classification_confidence,
           anonymous_client_hash,repeat_client,discovery_path,self_reported_source,traffic_kind,outcome_class,beta_version,meaningful,probe_class)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts,
            now,
            ev.get("request_id") or str(uuid.uuid4()),
            ep,
            1 if success else 0,
            ev.get("http_status"),
            ev.get("latency_ms"),
            size,
            ev.get("response_size_bytes"),
            ev.get("error_class"),
            ev.get("client_type"),
            ev.get("classification_confidence"),
            h,
            1 if seen else 0,
            ev.get("discovery_path"),
            ev.get("self_reported_source"),
            kind,
            ev.get("outcome_class"),
            ev.get("beta_version") or "0.16.1",
            meaningful,
            ev.get("probe_class"),
        ),
    )
    if meaningful:
        already = c.execute("SELECT 1 FROM first_external_use LIMIT 1").fetchone()
        if not already:
            c.execute(
                "INSERT INTO first_external_use(timestamp_utc,endpoint,latency_ms,success,self_reported_source) VALUES (?,?,?,?,?)",
                (ts, ep, ev.get("latency_ms"), 1, ev.get("self_reported_source")),
            )
    c.commit()
    c.close()


def first_external_use() -> dict | None:
    if not DB_PATH.exists():
        return None
    c = _conn()
    row = c.execute("SELECT * FROM first_external_use ORDER BY id ASC LIMIT 1").fetchone()
    c.close()
    return dict(row) if row else None
