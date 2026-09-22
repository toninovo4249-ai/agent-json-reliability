"""V186 passive 402 Index completion + real-buyer traffic filter. No self-buy. No new products."""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from products.beta.index_status import (
    BATCH_LIMIT,
    MAX_WINDOW_WAIT_SECONDS,
    apply_batch,
    counts as index_counts,
    load_status,
    mark_indexed_paths,
    mark_pending_retry,
    mark_result,
    next_submit_at,
    queue_ids,
    save_status,
    seconds_until_window,
)
from products.beta.landing import INDEXNOW_KEY, discovery_get_paths
from products.beta.product_registry import PRODUCTS
from products.beta.settings import ROOT, SYNTHETIC_HEADER

HOST = "https://agent-json-reliability.onrender.com"
ORIGIN = HOST
ORIGIN_ID = "d2c42ff7-e53e-4590-83eb-24fe022143f1"
X402SCAN_PAGE = f"https://www.x402scan.com/server/{ORIGIN_ID}"
REPORTS = ROOT / "reports"
UA = "x402-hunter-v186"
CTX = ssl.create_default_context()
HDR = {"User-Agent": UA, "Accept": "application/json,text/html,*/*"}
SYNTH = {SYNTHETIC_HEADER: "1", **HDR}


def _req(url: str, method: str = "GET", data: bytes | None = None, timeout: int = 35, headers: dict | None = None) -> tuple[int, str]:
    h = dict(headers or HDR)
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def _json(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 35) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    code, text = _req(url, method, data, timeout)
    try:
        return code, json.loads(text) if text else {}
    except json.JSONDecodeError:
        return code, text


def origin_health() -> dict[str, Any]:
    code, text = _req(HOST + "/health", headers=SYNTH)
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {"http": code, "raw": text[:400]}
    return data if isinstance(data, dict) else {"http": code}


def wait_live(max_wait: int = 30) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        h = origin_health()
        if h.get("ok") or h.get("alive"):
            return True
        time.sleep(min(2, max(0, deadline - time.time())))
    return False


def x402scan_check() -> dict[str, Any]:
    disc_code, disc = _json(
        "https://www.x402scan.com/api/trpc/public.resources.checkDiscovery",
        "POST",
        {"json": {"origin": ORIGIN}},
    )
    disc_json = {}
    if isinstance(disc, dict):
        disc_json = ((disc.get("result") or {}).get("data") or {}).get("json") or disc.get("json") or {}
    paid_n = 0
    resources = []
    if isinstance(disc_json, dict):
        resources = disc_json.get("resources") or []
        if isinstance(resources, list):
            paid_n = sum(1 for r in resources if isinstance(r, dict) and str(r.get("authMode") or "").lower() == "paid")
    return {
        "checkDiscovery_http": disc_code,
        "paid_resource_count": paid_n,
        "resourceCount": paid_n,
        "listed_resources": paid_n,
        "page": X402SCAN_PAGE,
        "found": bool((disc_json or {}).get("found")) if isinstance(disc_json, dict) else paid_n > 0,
    }


def x402scan_rescan_if_needed() -> dict[str, Any]:
    pre = x402scan_check()
    n = int(pre.get("paid_resource_count") or 0)
    if n >= 24:
        return {"pre": pre, "registerFromOrigin_http": None, "discovered": n, "status": "NO_REREGISTER_24_PAID"}
    code, body = _json(
        "https://www.x402scan.com/api/trpc/public.resources.registerFromOrigin?batch=1",
        "POST",
        {"0": {"json": {"origin": ORIGIN}}},
        timeout=90,
    )
    post = x402scan_check()
    pn = int(post.get("paid_resource_count") or 0)
    return {
        "pre": pre,
        "registerFromOrigin_http": code,
        "registerFromOrigin_body": str(body)[:800],
        "post": post,
        "discovered": pn,
        "status": "RESCAN_SAME_ORIGIN" if pn >= 24 else "RESCAN_STILL_SHORT",
    }


def _402index_listed() -> set[str]:
    listed: set[str] = set()
    for q in ("agent-json-reliability", "Agent Utility Store", "Fresh Web Evidence"):
        code, body = _json(f"https://402index.io/api/v1/services?q={urllib.parse.quote(q)}&protocol=x402&limit=50")
        items = []
        if isinstance(body, dict):
            items = body.get("services") or body.get("items") or body.get("results") or []
        if isinstance(body, list):
            items = body
        for it in items if isinstance(items, list) else []:
            url = str((it or {}).get("url") or "")
            if "agent-json-reliability.onrender.com" in url:
                listed.add(urllib.parse.urlparse(url).path or url)
    return listed


def indexnow_ping() -> dict[str, Any]:
    urls = [HOST + p for p in discovery_get_paths()]
    body = {
        "host": "agent-json-reliability.onrender.com",
        "key": INDEXNOW_KEY,
        "keyLocation": f"{HOST}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    code, text = _req("https://api.indexnow.org/indexnow", "POST", json.dumps(body).encode())
    return {"http": code, "url_count": len(urls), "body": str(text)[:300]}


def submit_402index_batch(wait: bool = False) -> dict[str, Any]:
    data = load_status()
    listed = _402index_listed()
    mark_indexed_paths(data, listed)
    wait_s = seconds_until_window(data)
    retry_at = next_submit_at(data)
    if wait_s > MAX_WINDOW_WAIT_SECONDS:
        marked = mark_pending_retry(data, retry_at, "hourly_cap_no_wait")
        c = index_counts(data)
        return {
            "skipped": True,
            "reason": "PENDING_RETRY",
            "wait_seconds": wait_s,
            "earliest_retry_at": retry_at.isoformat(),
            "pending_retry_ids": marked,
            "queued": queue_ids(data),
            "counts": c,
            "already_listed_paths": sorted(listed),
        }
    if wait and 0 < wait_s <= MAX_WINDOW_WAIT_SECONDS:
        time.sleep(wait_s)
        data = load_status()
        mark_indexed_paths(data, listed)
    by_id = {p["id"]: p for p in PRODUCTS}
    queued = queue_ids(data, BATCH_LIMIT)
    submitted = []
    for pid in queued:
        p = by_id[pid]
        payload = {
            "url": HOST + p["path"],
            "name": p["name"],
            "protocol": "x402",
            "http_method": "POST",
            "probe_body": json.dumps(
                {
                    "url": "https://example.com/",
                    "urls": ["https://example.com/", "https://example.org/"],
                    "text": "{'a': 1}",
                    "before": {"a": 1},
                    "after": {"a": 2},
                    "json": {"a": 1},
                    "schema": {"type": "object"},
                }
            ),
            "description": p["description"][:500],
            "price_usd": float(p["price_usdc"]),
            "payment_asset": "USDC",
            "payment_network": "Base",
            "category": p["category"],
            "provider": "toninovo4249-ai",
        }
        code, body = _json("https://402index.io/api/v1/register", "POST", payload, timeout=20)
        mark_result(data, pid, code, body)
        submitted.append({"id": pid, "http": code})
        if code == 429:
            mark_pending_retry(data, next_submit_at(data), "http_429")
            break
        time.sleep(0.2)
    if submitted:
        apply_batch(data, [s["id"] for s in submitted])
    else:
        save_status(data)
    c = index_counts(load_status())
    return {
        "skipped": False,
        "waited_seconds": 0,
        "submitted": submitted,
        "counts": c,
        "already_listed_paths": sorted(listed),
        "queued_next": queue_ids(load_status()),
        "earliest_retry_at": (load_status().get("earliest_retry_at") or next_submit_at().isoformat()),
    }


def blocker(h: dict[str, Any], idx_left: int, retry_at: str | None = None) -> tuple[str, str, str]:
    real402 = int(h.get("REAL_EXTERNAL_402_CALLS") or 0)
    attempts = int(h.get("PAYMENT_ATTEMPTS") or 0)
    paid = int(h.get("TOTAL_REAL_PAID_CALLS") or h.get("REAL_PAID_CALLS") or 0)
    if paid >= 1:
        return "NONE", "OBSERVE_REPEAT_USAGE_BEFORE_PRICE_CHANGE", "REAL_PAID_OBSERVE_REPEATS"
    if attempts >= 1:
        return "PAYMENT_FRICTION", "INSPECT_PAYMENT_FRICTION", "PAYMENT_ATTEMPT_NO_SETTLE"
    if real402 >= 1:
        return "OFFER_VALUE_OR_PRICE", "INSPECT_PRODUCT_VALUE_DESCRIPTION_PRICE", "REAL_402_NO_PAYMENT_ATTEMPT"
    if idx_left > 0:
        when = retry_at or "NEXT_ALLOWED_HOUR"
        return "DISCOVERY", f"RETRY_402INDEX_AFTER={when}_DO_NOT_ADD_PRODUCTS", "PASSIVE_INDEX_PENDING_RETRY_NO_REAL_BUYER"
    return "DISCOVERY", "DO_NOT_ADD_PRODUCTS_WAIT_FOR_REAL_EXTERNAL_402", "PASSIVE_INDEX_FILTER_LIVE_WAIT_FOR_REAL_BUYER"


def top_product(by_map: dict[str, int], key_lookup: dict[str, str]) -> str:
    if not by_map:
        return "none"
    path = max(by_map.items(), key=lambda kv: kv[1])[0]
    return key_lookup.get(path) or path or "none"


def monitor_fields(health: dict[str, Any], xs: dict[str, Any], idx: dict[str, Any]) -> dict[str, Any]:
    from products.beta.paid_ledger import paid_metrics, product_funnel_metrics, store_board

    c = idx if isinstance(idx, dict) and "INDEXED" in idx else index_counts()
    vs = 0
    try:
        vs = sum(int(product_funnel_metrics(p["id"], p["path"]).get("VERIFY_SUCCESS") or 0) for p in PRODUCTS)
    except Exception:
        vs = int(health.get("VERIFY_SUCCESS") or 0)
    path_to_id = {p["path"]: p["id"] for p in PRODUCTS}
    by402 = health.get("REAL_EXTERNAL_402_BY_ENDPOINT") or health.get("UNKNOWN_EXTERNAL_402_BY_ENDPOINT") or {}
    byatt = health.get("PAYMENT_ATTEMPTS_BY_ENDPOINT") or {}
    byrev: dict[str, float] = {}
    for p in PRODUCTS:
        m = paid_metrics(p["path"])
        byrev[p["id"]] = float(m.get("REAL_REVENUE_USDC") or 0)
    top_rev = "none"
    if byrev and max(byrev.values()) > 0:
        top_rev = max(byrev.items(), key=lambda kv: kv[1])[0]
    xs_n = xs.get("paid_resource_count") or xs.get("discovered") or xs.get("listed_resources") or 0
    try:
        xs_n = int(xs_n)
    except (TypeError, ValueError):
        xs_n = 0
    return {
        "PRODUCTS_LIVE": 24,
        "X402SCAN_PRODUCTS_VISIBLE": xs_n,
        "402INDEX_INDEXED": int(c.get("INDEXED") or 0),
        "402INDEX_PENDING": int(c.get("SUBMITTED_PENDING") or 0),
        "402INDEX_RATE_LIMITED": int(c.get("RATE_LIMITED") or 0) + int(c.get("PENDING_RETRY") or 0),
        "402INDEX_NOT_SUBMITTED": int(c.get("NOT_SUBMITTED") or 0),
        "402INDEX_PENDING_RETRY": int(c.get("PENDING_RETRY") or 0),
        "402INDEX_EARLIEST_RETRY_AT": load_status().get("earliest_retry_at") or next_submit_at().isoformat(),
        "DIRECTORY_402_PROBES": int(health.get("DIRECTORY_402_PROBES") or 0),
        "SYNTHETIC_402_PROBES": int(health.get("SYNTHETIC_402_PROBES") or 0),
        "REAL_EXTERNAL_FREE_CALLS": int(health.get("REAL_EXTERNAL_FREE_CALLS") or 0),
        "REAL_EXTERNAL_402_CALLS": int(health.get("REAL_EXTERNAL_402_CALLS") or 0),
        "PAYMENT_ATTEMPTS": int(health.get("PAYMENT_ATTEMPTS") or 0),
        "VERIFY_SUCCESS": vs,
        "REAL_PAID_CALLS": int(health.get("TOTAL_REAL_PAID_CALLS") or health.get("REAL_PAID_CALLS") or 0),
        "DISTINCT_REAL_PAID_BUYERS": int(health.get("TOTAL_DISTINCT_REAL_PAID_BUYERS") or 0),
        "REPEAT_REAL_PAID_BUYERS": int(health.get("TOTAL_REPEAT_REAL_PAID_BUYERS") or 0),
        "REAL_REVENUE_USDC": health.get("TOTAL_REAL_REVENUE_USDC") or 0,
        "TOP_PRODUCT_BY_REAL_EXTERNAL_402": top_product({str(k): int(v) for k, v in by402.items()}, path_to_id),
        "TOP_PRODUCT_BY_PAYMENT_ATTEMPTS": top_product({str(k): int(v) for k, v in byatt.items()}, path_to_id),
        "TOP_PRODUCT_BY_REAL_REVENUE": top_rev,
        "store_board": health.get("store_board") or store_board(),
    }


def copy_monitor(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "COPY_RESULT_BEGIN",
            "WORK_UNIT=X402_V186_PASSIVE_INDEX_COMPLETION_AND_REAL_BUYER_FILTER",
            f"PRODUCTS_LIVE={result.get('PRODUCTS_LIVE')}",
            f"X402SCAN_PRODUCTS_VISIBLE={result.get('X402SCAN_PRODUCTS_VISIBLE')}",
            f"402INDEX_INDEXED={result.get('402INDEX_INDEXED')}",
            f"402INDEX_PENDING={result.get('402INDEX_PENDING')}",
            f"402INDEX_RATE_LIMITED={result.get('402INDEX_RATE_LIMITED')}",
            f"402INDEX_NOT_SUBMITTED={result.get('402INDEX_NOT_SUBMITTED')}",
            f"DIRECTORY_402_PROBES={result.get('DIRECTORY_402_PROBES')}",
            f"REAL_EXTERNAL_402_CALLS={result.get('REAL_EXTERNAL_402_CALLS')}",
            f"PAYMENT_ATTEMPTS={result.get('PAYMENT_ATTEMPTS')}",
            f"REAL_PAID_CALLS={result.get('REAL_PAID_CALLS')}",
            f"DISTINCT_REAL_PAID_BUYERS={result.get('DISTINCT_REAL_PAID_BUYERS')}",
            f"REAL_REVENUE_USDC={result.get('REAL_REVENUE_USDC')}",
            "MONEY_SPENT_USD=0",
            f"EXACT_BLOCKER={result.get('EXACT_BLOCKER')}",
            f"NEXT_ACTION={result.get('NEXT_ACTION')}",
            f"FINAL_VERDICT={result.get('FINAL_VERDICT')}",
            "COPY_RESULT_END",
        ]
    )


def run_monitor() -> dict[str, Any]:
    h = origin_health()
    xs = x402scan_check()
    st = load_status()
    listed = _402index_listed()
    mark_indexed_paths(st, listed)
    save_status(st)
    c = index_counts(st)
    fields = monitor_fields(h, xs, c)
    left = int(c.get("NOT_SUBMITTED") or 0) + int(c.get("RATE_LIMITED") or 0) + int(c.get("PENDING_RETRY") or 0)
    retry_at = st.get("earliest_retry_at") or fields.get("402INDEX_EARLIEST_RETRY_AT")
    blk, nxt, verd = blocker(h, left, retry_at)
    fields.update(
        {
            "health": h,
            "x402scan": xs,
            "402index_status": c,
            "EXACT_BLOCKER": blk,
            "NEXT_ACTION": nxt,
            "FINAL_VERDICT": verd,
        }
    )
    return fields


def run_v186(wait_index: bool = False) -> dict[str, Any]:
    wait_live()
    xs = x402scan_rescan_if_needed()
    idx = submit_402index_batch(wait=wait_index)
    inn = indexnow_ping()
    mon = run_monitor()
    result = {
        "at": datetime.now(timezone.utc).isoformat(),
        **{k: mon.get(k) for k in (
            "PRODUCTS_LIVE",
            "X402SCAN_PRODUCTS_VISIBLE",
            "402INDEX_INDEXED",
            "402INDEX_PENDING",
            "402INDEX_RATE_LIMITED",
            "402INDEX_NOT_SUBMITTED",
            "DIRECTORY_402_PROBES",
            "SYNTHETIC_402_PROBES",
            "REAL_EXTERNAL_FREE_CALLS",
            "REAL_EXTERNAL_402_CALLS",
            "PAYMENT_ATTEMPTS",
            "VERIFY_SUCCESS",
            "REAL_PAID_CALLS",
            "DISTINCT_REAL_PAID_BUYERS",
            "REPEAT_REAL_PAID_BUYERS",
            "REAL_REVENUE_USDC",
            "TOP_PRODUCT_BY_REAL_EXTERNAL_402",
            "TOP_PRODUCT_BY_PAYMENT_ATTEMPTS",
            "TOP_PRODUCT_BY_REAL_REVENUE",
            "EXACT_BLOCKER",
            "NEXT_ACTION",
            "FINAL_VERDICT",
        )},
        "x402scan": xs,
        "402index": idx,
        "indexnow": inn,
        "MONEY_SPENT_USD": 0,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "latest_x402_v186_store.md"
    path.write_text("# V186\n\n```json\n" + json.dumps(result, indent=2, default=str)[:25000] + "\n```\n", encoding="utf-8")
    result["REPORT"] = str(path)
    return result
