"""V186 discovery amplifier refresh. No window wait. No self-buy. No new products."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from products.beta.discovery_surfaces import SURFACES, empty_row
from products.beta.index_status import counts as index_counts, load_status, next_submit_at
from products.beta.run_v186 import (
    HOST,
    _402index_listed,
    _json,
    _req,
    indexnow_ping,
    origin_health,
    submit_402index_batch,
    x402scan_check,
    x402scan_rescan_if_needed,
)
from products.beta.settings import ROOT
from products.beta.store_catalog import validate_bazaar_metadata

REPORTS = ROOT / "reports"
ORIGIN = HOST


def _our_text(blob: Any) -> bool:
    return "agent-json-reliability" in str(blob).lower() or "onrender.com" in str(blob).lower()


def check_circle() -> dict[str, Any]:
    code, body = _json("https://api.circle.com/v2/x402/discovery/resources?limit=50", timeout=20)
    items = []
    if isinstance(body, dict):
        items = body.get("resources") or body.get("data") or body.get("items") or []
    if isinstance(body, list):
        items = body
    ours = [it for it in items if isinstance(it, dict) and _our_text(it)]
    return empty_row(
        next(s for s in SURFACES if s["id"] == "circle_discovery"),
        INDEXED=bool(ours),
        SUBMITTED=True,
        PENDING=not bool(ours),
        http=code,
        matched=len(ours),
        CIRCLE_STATUS="INDEXED" if ours else "SUBMITTED_PENDING_APPROVAL",
    )


def check_mcp_registry() -> dict[str, Any]:
    url = "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.toninovo4249-ai%2Fagent-json-reliability"
    code, text = _req(url, timeout=20)
    indexed = code == 200 and "agent-json-reliability" in text.lower()
    return empty_row(next(s for s in SURFACES if s["id"] == "official_mcp_registry"), INDEXED=indexed, SUBMITTED=True, PENDING=not indexed, http=code)


def check_glama() -> dict[str, Any]:
    code, text = _req("https://glama.ai/mcp/servers?query=agent-json-reliability", timeout=20)
    indexed = code == 200 and "agent-json-reliability" in text.lower()
    return empty_row(next(s for s in SURFACES if s["id"] == "glama"), INDEXED=indexed, SUBMITTED=True, PENDING=not indexed, http=code)


def check_payai() -> dict[str, Any]:
    code, body = _json("https://facilitator.payai.network/supported", timeout=15)
    listed = False
    if isinstance(body, dict) and _our_text(body):
        listed = True
    return empty_row(
        next(s for s in SURFACES if s["id"] == "payai_bazaar"),
        INDEXED=listed,
        SUBMITTED=False,
        PENDING=not listed,
        http=code,
        PAYAI_BAZAAR_STATUS="REQUIRES_SETTLEMENT" if not listed else "INDEXED",
    )


def check_well_known() -> dict[str, Any]:
    paths = [
        "/.well-known/x402",
        "/.well-known/agent.json",
        "/.well-known/agent-services.json",
        "/openapi.json",
        "/skill.md",
        "/llms.txt",
        "/AGENTS.md",
        "/v1/catalog",
    ]
    checks = {}
    abs_ok = True
    for p in paths:
        code, text = _req(HOST + p, timeout=15)
        checks[p] = code
        if code != 200:
            abs_ok = False
        if "localhost" in text.lower() or "trycloudflare" in text.lower() or "ngrok" in text.lower():
            if p in {"/openapi.json", "/.well-known/agent.json", "/skill.md", "/llms.txt", "/AGENTS.md"}:
                abs_ok = False
    return {"pass": abs_ok and all(v == 200 for v in checks.values()), "checks": checks}


def discovery_map(xs: dict[str, Any], idx_counts: dict[str, int], circle: dict, mcp: dict, glama: dict, payai: dict) -> list[dict[str, Any]]:
    xs_n = int(xs.get("paid_resource_count") or 0)
    rows = [
        circle,
        empty_row(
            next(s for s in SURFACES if s["id"] == "x402scan"),
            INDEXED=xs_n >= 24,
            SUBMITTED=True,
            PENDING=xs_n < 24,
            products=xs_n,
        ),
        payai,
        empty_row(next(s for s in SURFACES if s["id"] == "x402_facilitators"), INDEXED=False, SUBMITTED=False, PENDING=True),
        empty_row(
            next(s for s in SURFACES if s["id"] == "402index"),
            INDEXED=int(idx_counts.get("INDEXED") or 0) > 0,
            SUBMITTED=int(idx_counts.get("SUBMITTED_PENDING") or 0) > 0,
            PENDING=True,
            indexed=int(idx_counts.get("INDEXED") or 0),
            pending=int(idx_counts.get("SUBMITTED_PENDING") or 0),
            rate_limited=int(idx_counts.get("RATE_LIMITED") or 0) + int(idx_counts.get("PENDING_RETRY") or 0),
            rejected=int(idx_counts.get("REJECTED") or 0),
        ),
        mcp,
        glama,
        empty_row(next(s for s in SURFACES if s["id"] == "x402_aggregators"), INDEXED=xs_n >= 24, SUBMITTED=True, PENDING=False),
        empty_row(next(s for s in SURFACES if s["id"] == "indexnow"), INDEXED=True, SUBMITTED=True, PENDING=False),
    ]
    return rows


def copy_refresh(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "COPY_RESULT_BEGIN",
            "WORK_UNIT=X402_V186_DISCOVERY_AMPLIFIER_MACHINE_TRAFFIC",
            f"DISCOVERY_SURFACES_FOUND={result.get('DISCOVERY_SURFACES_FOUND')}",
            f"DISCOVERY_SURFACES_INDEXED={result.get('DISCOVERY_SURFACES_INDEXED')}",
            f"CIRCLE_STATUS={result.get('CIRCLE_STATUS')}",
            f"X402SCAN_PRODUCTS={result.get('X402SCAN_PRODUCTS')}",
            f"402INDEX_INDEXED={result.get('402INDEX_INDEXED')}",
            f"PAYAI_BAZAAR_STATUS={result.get('PAYAI_BAZAAR_STATUS')}",
            f"BAZAAR_METADATA_PASS={result.get('BAZAAR_METADATA_PASS')}",
            f"SKILL_MD_READY={result.get('SKILL_MD_READY')}",
            f"CATALOG_READY={result.get('CATALOG_READY')}",
            f"SELECTOR_READY={result.get('SELECTOR_READY')}",
            f"MCP_DISCOVERY_TOOLS_READY={result.get('MCP_DISCOVERY_TOOLS_READY')}",
            f"WELL_KNOWN_DISCOVERY_PASS={result.get('WELL_KNOWN_DISCOVERY_PASS')}",
            f"AUTO_SUBMISSIONS_EXECUTED={result.get('AUTO_SUBMISSIONS_EXECUTED')}",
            f"CATALOG_EXTERNAL_VIEWS={result.get('CATALOG_EXTERNAL_VIEWS')}",
            f"SELECTOR_EXTERNAL_CALLS={result.get('SELECTOR_EXTERNAL_CALLS')}",
            f"MCP_DISCOVERY_CALLS={result.get('MCP_DISCOVERY_CALLS')}",
            f"REAL_EXTERNAL_AGENT_402_CALLS={result.get('REAL_EXTERNAL_AGENT_402_CALLS')}",
            f"PAYMENT_ATTEMPTS={result.get('PAYMENT_ATTEMPTS')}",
            f"REAL_PAID_CALLS={result.get('REAL_PAID_CALLS')}",
            f"REAL_REVENUE_USDC={result.get('REAL_REVENUE_USDC')}",
            "MONEY_SPENT_USD=0",
            f"EXACT_BLOCKER={result.get('EXACT_BLOCKER')}",
            f"NEXT_ACTION={result.get('NEXT_ACTION')}",
            f"FINAL_VERDICT={result.get('FINAL_VERDICT')}",
            "COPY_RESULT_END",
        ]
    )


def run_v186_discovery_refresh() -> dict[str, Any]:
    from products.beta.store_catalog import select_products

    bazaar_missing = validate_bazaar_metadata()
    xs = x402scan_rescan_if_needed()
    idx = submit_402index_batch(wait=False)
    inn = indexnow_ping()
    circle = check_circle()
    mcp = check_mcp_registry()
    glama = check_glama()
    payai = check_payai()
    wk = check_well_known()
    cat_code, cat = _json(HOST + "/v1/catalog", timeout=20)
    sel_code, sel = _json(HOST + "/v1/catalog/select", "POST", {"task": "compare two URLs"}, timeout=20)
    skill_code, skill = _req(HOST + "/skill.md", timeout=15)
    mcp_code, mcp_list = _json(HOST + "/mcp", "POST", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=15)
    tools = []
    if isinstance(mcp_list, dict):
        tools = ((mcp_list.get("result") or {}).get("tools") or [])
    tool_names = {t.get("name") for t in tools if isinstance(t, dict)}
    local_sel = select_products("repair JSON")
    h = origin_health()
    st = load_status()
    c = index_counts(st)
    listed = _402index_listed()
    surfaces = discovery_map(xs, c, circle, mcp, glama, payai)
    indexed_n = sum(1 for s in surfaces if s.get("INDEXED"))
    auto = []
    if idx.get("skipped"):
        auto.append("402index_PENDING_RETRY")
    elif idx.get("submitted"):
        auto.append(f"402index_submitted={len(idx.get('submitted') or [])}")
    if inn.get("http") in {200, 202}:
        auto.append(f"indexnow={inn.get('http')}")
    if xs.get("registerFromOrigin_http"):
        auto.append("x402scan_rescan_same_origin")
    real402 = int(h.get("REAL_EXTERNAL_AGENT_402_CALLS") or h.get("REAL_EXTERNAL_402_CALLS") or 0)
    attempts = int(h.get("PAYMENT_ATTEMPTS") or 0)
    paid = int(h.get("TOTAL_REAL_PAID_CALLS") or 0)
    if paid:
        blk, nxt, verd = "NONE", "OBSERVE_REPEAT_USAGE", "REAL_PAID"
    elif attempts:
        blk, nxt, verd = "PAYMENT_FRICTION", "INSPECT_PAYMENT_FRICTION", "ATTEMPT_NO_SETTLE"
    elif real402:
        blk, nxt, verd = "OFFER_VALUE_OR_PRICE", "INSPECT_PRODUCT_VALUE_DESCRIPTION_PRICE", "AGENT_402_NO_PAY"
    else:
        retry = st.get("earliest_retry_at") or next_submit_at(st).isoformat()
        blk, nxt, verd = (
            "DISCOVERY",
            f"KEEP_PASSIVE_INDEX_RETRY_402INDEX_AFTER={retry}_DO_NOT_ADD_PRODUCTS",
            "DISCOVERY_AMPLIFIER_LIVE_WAIT_FOR_REAL_AGENT_402",
        )
    xs_n = int(xs.get("discovered") or xs.get("paid_resource_count") or 0)
    result = {
        "at": datetime.now(timezone.utc).isoformat(),
        "DISCOVERY_SURFACES_FOUND": len(surfaces),
        "DISCOVERY_SURFACES_INDEXED": indexed_n,
        "CIRCLE_STATUS": circle.get("CIRCLE_STATUS") or ("INDEXED" if circle.get("INDEXED") else "SUBMITTED_PENDING_APPROVAL"),
        "X402SCAN_PRODUCTS": xs_n,
        "402INDEX_INDEXED": int(c.get("INDEXED") or 0),
        "402INDEX_PENDING": int(c.get("SUBMITTED_PENDING") or 0),
        "402INDEX_RATE_LIMITED": int(c.get("RATE_LIMITED") or 0) + int(c.get("PENDING_RETRY") or 0),
        "402INDEX_REJECTED": int(c.get("REJECTED") or 0),
        "402INDEX_EARLIEST_RETRY_AT": st.get("earliest_retry_at") or next_submit_at(st).isoformat(),
        "PAYAI_BAZAAR_STATUS": payai.get("PAYAI_BAZAAR_STATUS") or "REQUIRES_SETTLEMENT",
        "BAZAAR_METADATA_PASS": not bazaar_missing,
        "BAZAAR_MISSING": bazaar_missing,
        "SKILL_MD_READY": skill_code == 200 and "Catalog:" in skill,
        "CATALOG_READY": cat_code == 200 and int((cat or {}).get("product_count") or 0) == 24,
        "SELECTOR_READY": sel_code == 200 and (sel or {}).get("top") == "evidence_compare" and len((sel or {}).get("matches") or []) >= 1,
        "MCP_DISCOVERY_TOOLS_READY": {"list_paid_products", "select_paid_product"} <= tool_names,
        "WELL_KNOWN_DISCOVERY_PASS": bool(wk.get("pass")),
        "AUTO_SUBMISSIONS_EXECUTED": auto,
        "CATALOG_EXTERNAL_VIEWS": int(h.get("CATALOG_VIEWS") or h.get("CATALOG_EXTERNAL_VIEWS") or 0),
        "SELECTOR_EXTERNAL_CALLS": int(h.get("SELECTOR_CALLS") or h.get("CATALOG_EXTERNAL_SELECTIONS") or 0),
        "MCP_DISCOVERY_CALLS": int(h.get("MCP_DISCOVERY_TOOL_CALLS") or 0),
        "REAL_EXTERNAL_AGENT_402_CALLS": real402,
        "PAYMENT_ATTEMPTS": attempts,
        "REAL_PAID_CALLS": paid,
        "REAL_REVENUE_USDC": h.get("TOTAL_REAL_REVENUE_USDC") or 0,
        "MONEY_SPENT_USD": 0,
        "EXACT_BLOCKER": blk,
        "NEXT_ACTION": nxt,
        "FINAL_VERDICT": verd,
        "surfaces": surfaces,
        "well_known": wk,
        "402index": idx,
        "indexnow": inn,
        "x402scan": xs,
        "local_select_repair": local_sel.get("top"),
        "402index_listed_paths": sorted(listed),
        "health": {k: h.get(k) for k in (
            "REAL_EXTERNAL_AGENT_402_CALLS",
            "REAL_EXTERNAL_402_CALLS",
            "DIRECTORY_402_PROBES",
            "PAYMENT_ATTEMPTS",
            "TOTAL_REAL_PAID_CALLS",
            "CATALOG_VIEWS",
            "SELECTOR_CALLS",
            "SKILL_MD_VIEWS",
            "MCP_DISCOVERY_TOOL_CALLS",
        )},
        "PRODUCTS_LIVE": 24,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "latest_x402_v186_discovery_amplifier.md"
    path.write_text("# V186 amplifier\n\n```json\n" + json.dumps(result, indent=2, default=str)[:25000] + "\n```\n", encoding="utf-8")
    result["REPORT"] = str(path)
    return result
