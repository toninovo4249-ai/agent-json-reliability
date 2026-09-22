from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from products.agent_json_reliability.inspect import inspect_json
from products.agent_json_reliability.repair import repair_json
from products.agent_json_reliability.reliable import reliable_json
from products.agent_json_reliability.validate import validate_json
from products.beta.batch import reliable_batch
from products.beta.catalog import public_catalog
from products.beta.identity import client_hash, traffic_kind, ua_coarse
from products.beta.landing import (
    INDEXNOW_KEY,
    OPENAPI_DESCRIPTION,
    agents_md,
    landing_html,
    llms_full_txt,
    llms_txt,
    robots_txt,
    sitemap_xml,
    well_known_agent_json,
)
from products.beta.security import schema_limits, walk_limits
from products.beta.selfcheck import ready_selfcheck
from products.beta.settings import (
    BATCH_PUBLIC,
    BETA_VERSION,
    ENABLE_HTML_BETA,
    FIRST_PAID_BUYER_MODE,
    FREE_BETA,
    MAX_ARRAY_LEN,
    MAX_BATCH,
    MAX_CONCURRENT_REQUESTS,
    MAX_JSON_DEPTH,
    MAX_NODES,
    MAX_OBJECT_KEYS,
    MAX_REQUEST_BODY_BYTES,
    MAX_REQUESTS_PER_MINUTE_PER_SESSION,
    MAX_SCHEMA_DEPTH,
    MAX_STRING_CHARS,
    MAINNET_PAYMENT_ENABLED,
    PAID_PRICE_USDC,
    EVIDENCE_PRICE_USDC,
    PAID_ROUTE_ENABLED,
    PAYMENT_REQUIRED,
    PUBLIC_BETA_CONFIRM,
    PUBLIC_PATHS,
    X402_NETWORK,
    X402_PAYMENT_ENABLED,
    current_base_url,
    discovery_server_url,
    public_exposure_mode,
)
from products.beta.acquisition import acquisition_metrics
from products.beta.cdp_jwt import cdp_auth_configured
from products.beta.paid_ledger import record_paid_call, record_product_event, split_paid_metrics
from products.beta.product_registry import PRODUCTS, active_paid_products, product_by_path
from products.beta.store_catalog import META, catalog_payload, select_products
from products.agent_utility.handlers import run_product
from products.beta.store import record_v16
from products.beta.x402_gate import (
    PAID_AJR,
    PAID_EVIDENCE,
    PAID_HTTP_PATHS,
    amount_for_path,
    atomic_amount,
    configured_asset,
    configured_network,
    encode_payment_response,
    evidence_atomic_amount,
    evidence_payment_flags_on,
    maybe_payment_response,
    payment_flags_on,
    price_usdc_for_path,
    seller_receive_address,
    settle_payment,
    valid_seller_receive_address,
)
from products.fresh_web_evidence.metrics import evidence_metrics, record_pack
from products.fresh_web_evidence.pack import build_pack
from products.gateway.mcp_server import handle_rpc
from products.gateway.rate_limit import RateLimiter

ALLOWED_PREFIX = (
    "/v1/json/",
    "/v1/evidence/",
    "/v1/web/",
    "/v1/url/",
    "/v1/api/",
    "/v1/mcp/",
    "/v1/x402/",
    "/v1/catalog",
    "/.well-known/",
)


def _tool_path(path: str) -> bool:
    return path.startswith(("/v1/json", "/v1/evidence", "/v1/web", "/v1/url", "/v1/api", "/v1/mcp/", "/v1/x402", "/v1/catalog"))


class BetaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        if len(request.headers) > 60:
            return JSONResponse({"error": "header_abuse", "error_class": "header_abuse"}, status_code=400)
        for k, v in request.headers.items():
            if len(k) + len(v) > 8192:
                return JSONResponse({"error": "header_abuse", "error_class": "header_abuse"}, status_code=400)
        limiter = request.app.state.limiter
        sem = request.app.state.sem
        ua = request.headers.get("user-agent")
        path = request.url.path
        src = request.query_params.get("source")
        ctype, conf = ua_coarse(ua)
        ch = client_hash(request.client.host if request.client else None, ua)
        kind = traffic_kind(request.headers, ua, request.client.host if request.client else None, path, source=src)
        pay_sig_early = bool(request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature"))
        unpaid_paid = path in PAID_HTTP_PATHS and not pay_sig_early
        directory_probe = kind in {"DIRECTORY_PROBE", "LIKELY_CRAWLER", "HEALTH_MONITOR"}
        skip_quota = unpaid_paid or (directory_probe and not pay_sig_early)
        acquired_sem = False
        if _tool_path(path) and not skip_quota:
            if not limiter.allow(ch):
                record_v16(
                    {
                        "endpoint": path,
                        "success": False,
                        "http_status": 429,
                        "latency_ms": 0,
                        "request_size_bytes": 0,
                        "response_size_bytes": 0,
                        "error_class": "rate_limited",
                        "client_type": ctype,
                        "classification_confidence": conf,
                        "anonymous_client_hash": ch,
                        "traffic_kind": kind,
                        "self_reported_source": src,
                        "beta_version": BETA_VERSION,
                        "probe_class": "rate_limit",
                    }
                )
                return JSONResponse({"error": "rate_limited", "error_class": "rate_limited"}, status_code=429)
            if not sem.acquire(blocking=False):
                return JSONResponse({"error": "too_many_concurrent", "error_class": "concurrency"}, status_code=429)
            acquired_sem = True
        try:
            body = await request.body()
        except Exception:
            body = b""
        if len(body) > MAX_REQUEST_BODY_BYTES:
            if acquired_sem:
                sem.release()
            return JSONResponse({"error": "payload too large", "error_class": "oversized"}, status_code=413)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = StarletteRequest(request.scope, receive)
        request.state.body = body
        request.state.traffic_kind = kind
        request.state.client_hash = ch
        resp = None
        try:
            # Unpaid paid-route probes must 402 before FastAPI body/schema validation.
            if path in PAID_HTTP_PATHS:
                sig = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature")
                if not sig:
                    pay_block = maybe_payment_response(request, path)
                    if pay_block is not None:
                        resp = pay_block
            if resp is None:
                resp = await call_next(request)
        finally:
            if acquired_sem:
                try:
                    sem.release()
                except ValueError:
                    pass
        lat = (time.perf_counter() - t0) * 1000
        disc = path if path in {
            "/",
            "/.well-known/agent-services.json",
            "/capabilities",
            "/openapi.json",
            "/health",
            "/ready",
            "/llms.txt",
            "/llms-full.txt",
            "/AGENTS.md",
            "/robots.txt",
            "/sitemap.xml",
            "/.well-known/x402",
            "/.well-known/agent.json",
            "/.well-known/agent-products.json",
            "/v1/catalog",
            "/products",
            "/mcp",
        } else None
        probe = None
        if resp.status_code == 404 and path not in PUBLIC_PATHS and not path.startswith("/v1/json"):
            probe = "RANDOM_PROBE"
            if kind == "REAL_EXTERNAL_UNKNOWN":
                kind = "RANDOM_PROBE"
        pay_sig = bool(request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature"))
        if path in PAID_HTTP_PATHS and pay_sig:
            probe = "payment_attempt"
        mcp_product_call = False
        if path == "/mcp":
            try:
                mcp_product_call = json.loads(body or b"{}").get("method") == "tools/call"
            except Exception:
                mcp_product_call = False
        track = path.startswith("/v1/") or disc is not None or probe is not None
        if track:
            rsize = int(resp.headers.get("content-length") or 0)
            record_v16(
                {
                    "request_id": str(uuid.uuid4()),
                    "endpoint": path[:200],
                    "success": 200 <= resp.status_code < 400,
                    "http_status": resp.status_code,
                    "latency_ms": lat,
                    "request_size_bytes": len(body),
                    "response_size_bytes": rsize,
                    "error_class": None if resp.status_code < 400 else f"http_{resp.status_code}",
                    "client_type": ctype,
                    "classification_confidence": conf,
                    "anonymous_client_hash": ch,
                    "discovery_path": disc if not mcp_product_call else None,
                    "self_reported_source": src,
                    "traffic_kind": kind,
                    "outcome_class": getattr(request.state, "outcome_class", None),
                    "beta_version": BETA_VERSION,
                    "probe_class": probe,
                    "mcp_product_call": mcp_product_call,
                }
            )
        return resp


def _read(request: Request) -> dict[str, Any]:
    raw = getattr(request.state, "body", b"") or b"{}"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(400, "invalid_utf8") from e

    def _pairs(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise HTTPException(400, "duplicate_keys")
        return dict(pairs)

    try:
        return json.loads(text, object_pairs_hook=_pairs)
    except json.JSONDecodeError as e:
        raise HTTPException(400, "invalid_json") from e


def _guard_value(obj: Any, schema: Any | None) -> None:
    err = walk_limits(
        obj,
        max_depth=MAX_JSON_DEPTH,
        max_nodes=MAX_NODES,
        max_arr=MAX_ARRAY_LEN,
        max_keys=MAX_OBJECT_KEYS,
        max_str=MAX_STRING_CHARS,
    )
    if err:
        raise HTTPException(400, err)
    serr = schema_limits(schema, max_depth=MAX_SCHEMA_DEPTH)
    if serr:
        raise HTTPException(400, serr)


def _x_payment_info(path: str) -> dict[str, Any]:
    pay_to = seller_receive_address() if valid_seller_receive_address() else ""
    return {
        "price": {"mode": "fixed", "currency": "USD", "amount": str(price_usdc_for_path(path))},
        "protocols": [
            {
                "x402": {
                    "scheme": "exact",
                    "network": configured_network(),
                    "asset": configured_asset(),
                    "amount": amount_for_path(path),
                    "payTo": pay_to,
                }
            }
        ],
    }


def _finish_paid(request: Request, path: str, result: Any, tpay: float, product_id: str, price: str):
    if not getattr(request.state, "x402_verified", None):
        return result
    receipt = settle_payment(request.state.x402_verified, getattr(request.state, "x402_payload", None), path)
    record_paid_call(
        {
            "endpoint": path,
            "product_id": product_id,
            "payer": receipt.get("payer"),
            "network": receipt.get("network") or X402_NETWORK,
            "asset": receipt.get("asset") or "USDC",
            "price": receipt.get("price") or price,
            "usd_price": receipt.get("price") or price,
            "amount_atomic": receipt.get("amount"),
            "payTo": receipt.get("payTo"),
            "tx_hash": receipt.get("tx_hash"),
            "payment_hash": receipt.get("payment_hash"),
            "nonce": receipt.get("nonce"),
            "verify_status": receipt.get("verify_status"),
            "settlement_status": receipt.get("settlement_status"),
            "response_status": 200 if receipt.get("settlement_status") in {"settled", "mock_settled"} else 402,
            "processing_ms": (time.perf_counter() - tpay) * 1000,
            "is_real": bool(receipt.get("is_real")),
        }
    )
    if receipt.get("settlement_status") == "settled":
        resp = JSONResponse(result)
        resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
        return resp
    if receipt.get("settlement_status") == "mock_settled":
        resp = JSONResponse(result)
        resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
        resp.headers["X-AJR-SETTLEMENT"] = "MOCK_NOT_REAL"
        return resp
    return JSONResponse(
        {"error": "settlement_failed", "settlement_status": receipt.get("settlement_status"), "is_real": False},
        status_code=402,
    )


def create_json_beta_app() -> FastAPI:
    limiter = RateLimiter(per_minute=MAX_REQUESTS_PER_MINUTE_PER_SESSION, burst=max(5, MAX_REQUESTS_PER_MINUTE_PER_SESSION // 3))
    sem = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
    app = FastAPI(
        title="Agent JSON Reliability",
        version=BETA_VERSION,
        description=OPENAPI_DESCRIPTION,
        servers=[{"url": discovery_server_url(), "description": "Public origin"}],
        docs_url=None,
        redoc_url=None,
    )
    app.state.limiter = limiter
    app.state.sem = sem
    app.add_middleware(BetaMiddleware)

    def custom_openapi():
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        server = discovery_server_url()
        schema["servers"] = [{"url": server, "description": "Public origin"}]
        schema["info"]["description"] = OPENAPI_DESCRIPTION
        schema["info"]["contact"] = {
            "url": "https://github.com/toninovo4249-ai/agent-json-reliability",
        }
        schema["info"]["license"] = {"name": "MIT"}
        schema["info"]["x-llm-required"] = False
        schema["info"]["x-guidance"] = (
            "Free routes: GET /health, POST /v1/json/inspect, POST /v1/json/validate, "
            "POST /v1/json/repair, POST /mcp. "
            "Paid Agent Utility Store routes are listed per-path with x-payment-info. "
            "AJR remains 0.003 USDC. Evidence Pack remains 0.0075 USDC. "
            "Unpaid calls to paid routes return HTTP 402. Pay-per-call Base USDC x402."
        )
        schema["info"].pop("x-payment-required", None)
        schema["info"].pop("x-x402-paid-path", None)
        schema["security"] = []
        comps = schema.setdefault("components", {})
        comps.pop("securitySchemes", None)
        pay_to = seller_receive_address() if valid_seller_receive_address() else ""
        x_payment_info = {
            "price": {"mode": "fixed", "currency": "USD", "amount": "0.003"},
            "protocols": [
                {
                    "x402": {
                        "scheme": "exact",
                        "network": configured_network(),
                        "asset": configured_asset(),
                        "amount": atomic_amount(),
                        "payTo": pay_to,
                    }
                }
            ],
        }
        x_payment_info_evidence = {
            "price": {"mode": "fixed", "currency": "USD", "amount": "0.0075"},
            "protocols": [
                {
                    "x402": {
                        "scheme": "exact",
                        "network": configured_network(),
                        "asset": configured_asset(),
                        "amount": evidence_atomic_amount(),
                        "payTo": pay_to,
                    }
                }
            ],
        }
        reliable_body = {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "Malformed or valid JSON text from an agent"},
                "schema": {"type": "object", "description": "Optional JSON Schema"},
            },
        }
        reliable_200 = {
            "type": "object",
            "properties": {
                "valid_original": {"type": "boolean"},
                "repaired": {"type": "boolean"},
                "valid_final": {"type": "boolean"},
                "schema_valid": {"type": "boolean"},
                "unsafe_or_ambiguous": {"type": "boolean"},
                "json": {},
                "errors": {"type": "array"},
                "changes": {"type": "array"},
            },
        }
        paths = schema.setdefault("paths", {})
        if not BATCH_PUBLIC:
            paths.pop("/v1/json/reliable/batch", None)
        for path, item in list(paths.items()):
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if method not in {"get", "put", "post", "delete", "patch", "options", "head"}:
                    continue
                if not isinstance(op, dict):
                    continue
                op["security"] = []
                op.pop("x-payment-required", None)
                op.pop("x-x402", None)
                paid_ajr = path == PAID_AJR and method == "post"
                paid_ev = path == PAID_EVIDENCE and method == "post" and evidence_payment_flags_on()
                prod = product_by_path(path)
                paid_store = (
                    method == "post"
                    and prod is not None
                    and prod["id"] not in {"json_reliable", "evidence_pack"}
                    and prod in active_paid_products()
                )
                if paid_ajr:
                    op["summary"] = "Paid x402 JSON reliability"
                    op["description"] = (
                        "Paid x402 v2 exact route. Unpaid requests return HTTP 402 with PAYMENT-REQUIRED. "
                        "0.003 USDC on Base (eip155:8453). Inspect, validate, repair, and MCP remain free."
                    )
                    op["x-payment-info"] = x_payment_info
                    op["requestBody"] = {
                        "required": True,
                        "content": {"application/json": {"schema": reliable_body}},
                    }
                    responses = op.setdefault("responses", {})
                    responses["200"] = {
                        "description": "JSON reliability result after payment",
                        "content": {"application/json": {"schema": reliable_200}},
                    }
                    responses["402"] = {"description": "Payment Required"}
                elif paid_ev:
                    op["summary"] = "Paid x402 Fresh Web Evidence Pack"
                    op["description"] = (
                        "Fresh Web Evidence Pack for AI agents. "
                        "Fetches up to 5 public URLs at request time and returns structured facts with source URLs, "
                        "UTC timestamps, SHA-256 provenance, and explicit contradictions. "
                        "0.0075 USDC per pack on Base. Unpaid requests return HTTP 402. "
                        "Payment is verified before any outbound fetch."
                    )
                    op["x-payment-info"] = x_payment_info_evidence
                    op["requestBody"] = {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {"type": "string"},
                                        "urls": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                                    },
                                }
                            }
                        },
                    }
                    responses = op.setdefault("responses", {})
                    responses["200"] = {"description": "Evidence pack after payment"}
                    responses["402"] = {"description": "Payment Required"}
                elif paid_store and prod:
                    op["summary"] = f"Paid x402 {prod['name']}"
                    op["description"] = (
                        f"{prod['description']} {prod['price_usdc']} USDC per call on Base via x402. "
                        "Unpaid requests return HTTP 402. Payment is verified before outbound fetch."
                    )
                    op["x-payment-info"] = _x_payment_info(path)
                    schema_in = (META.get(prod["id"]) or {}).get("input_schema") or {"type": "object"}
                    op["requestBody"] = {
                        "required": True,
                        "content": {"application/json": {"schema": schema_in}},
                    }
                    responses = op.setdefault("responses", {})
                    responses["200"] = {"description": f"{prod['name']} after payment"}
                    responses["402"] = {"description": "Payment Required"}
        return schema

    app.openapi = custom_openapi

    @app.get("/", response_class=HTMLResponse)
    def root():
        return landing_html()

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "alive": True,
            "FREE_BETA": FREE_BETA,
            "PAYMENT_REQUIRED": PAYMENT_REQUIRED,
            "PUBLIC_BETA_CONFIRM": PUBLIC_BETA_CONFIRM,
            "PUBLIC_EXPOSURE_MODE": public_exposure_mode(),
            "primary": "/v1/json/reliable",
            "x402_payment_integrated": payment_flags_on(),
            "X402_PAYMENT_ENABLED": X402_PAYMENT_ENABLED,
            "PAID_ROUTE_ENABLED": PAID_ROUTE_ENABLED,
            "MAINNET_PAYMENT_ENABLED": MAINNET_PAYMENT_ENABLED,
            "FIRST_PAID_BUYER_MODE": FIRST_PAID_BUYER_MODE,
            "x402_middleware_present": True,
            "seller_receive_configured": valid_seller_receive_address(),
            "cdp_auth_configured": cdp_auth_configured(),
            **split_paid_metrics(),
            **acquisition_metrics(),
            "fresh_web_evidence": evidence_metrics(),
        }

    @app.get("/ready")
    def ready():
        chk = ready_selfcheck()
        if not chk["ready"]:
            raise HTTPException(503, "not_ready")
        return chk

    @app.get("/capabilities")
    def capabilities():
        return {
            "FREE_BETA": True,
            "PAYMENT_REQUIRED": False,
            "primary": "/v1/json/reliable",
            "primary_capability": "json_reliable",
            "paid_route": "/v1/json/reliable" if payment_flags_on() else None,
            "paid_routes": [p["path"] for p in active_paid_products()],
            "free_routes": [
                "/v1/json/inspect",
                "/v1/json/validate",
                "/v1/json/repair",
                "/mcp",
                "/v1/catalog",
                "/v1/catalog/select",
            ],
            "tools": [s["tool_name"] for s in public_catalog()["services"]],
            "html_exposed": ENABLE_HTML_BETA,
        }

    @app.get("/.well-known/agent-services.json")
    def manifest():
        return public_catalog()

    @app.get("/v1/catalog")
    def catalog_get():
        return catalog_payload()

    @app.get("/products")
    def products_get():
        return catalog_payload()

    @app.get("/.well-known/agent-products.json")
    def agent_products():
        return catalog_payload()

    @app.post("/v1/catalog/select")
    async def catalog_select(request: Request):
        body = _read(request)
        task = str(body.get("task") or "")
        try:
            return select_products(task)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/.well-known/x402")
    def well_known_x402():
        base = discovery_server_url()
        resources = [f"{base}{p['path']}" for p in active_paid_products()]
        n = len(resources)
        instructions = (
            f"Agent Utility Store: {n} paid x402 resources. "
            "POST /v1/json/reliable is 0.003 USDC. POST /v1/evidence/pack is 0.0075 USDC. "
            "inspect/validate/repair and MCP stay free. Pay-per-call Base USDC."
        )
        return {
            "version": 1,
            "resources": resources,
            "instructions": instructions,
        }

    @app.get("/.well-known/agent.json")
    def well_known_agent():
        return well_known_agent_json()

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return robots_txt()

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms():
        return llms_txt()

    @app.get("/llms-full.txt", response_class=PlainTextResponse)
    def llms_full():
        return llms_full_txt()

    @app.get("/AGENTS.md", response_class=PlainTextResponse)
    def agents():
        return agents_md()

    @app.get("/sitemap.xml", response_class=PlainTextResponse)
    def sitemap():
        return PlainTextResponse(sitemap_xml(), media_type="application/xml")

    @app.get(f"/{INDEXNOW_KEY}.txt", response_class=PlainTextResponse)
    def indexnow_key():
        return INDEXNOW_KEY

    @app.post("/mcp")
    async def mcp(request: Request):
        body = _read(request)
        return handle_rpc(body)

    @app.post("/v1/json/inspect")
    async def inspect(request: Request):
        body = _read(request)
        _guard_value(body, None)
        if not str(body.get("text") or "").strip():
            raise HTTPException(400, "empty_text")
        return inspect_json(str(body.get("text") or ""))

    @app.post("/v1/json/validate")
    async def validate(request: Request):
        body = _read(request)
        if "instance" not in body:
            raise HTTPException(400, "instance required")
        schema = body.get("schema")
        _guard_value(body.get("instance"), schema if isinstance(schema, dict) else None)
        return validate_json(body.get("instance"), schema if isinstance(schema, dict) else None)

    @app.post("/v1/json/repair")
    async def repair(request: Request):
        body = _read(request)
        text = str(body.get("text") or "")
        if not text.strip():
            raise HTTPException(400, "empty_text")
        if len(text) > MAX_REQUEST_BODY_BYTES:
            raise HTTPException(413, "oversized")
        return repair_json(text, body.get("mode") or "safe")

    @app.post("/v1/json/reliable")
    async def reliable(request: Request):
        tpay = time.perf_counter()
        blocked = maybe_payment_response(request, "/v1/json/reliable")
        if blocked is not None:
            if payment_flags_on() and blocked.status_code != 402:
                record_paid_call(
                    {
                        "endpoint": "/v1/json/reliable",
                        "product_id": "json_reliable",
                        "payer": None,
                        "network": X402_NETWORK,
                        "asset": "USDC",
                        "price": str(PAID_PRICE_USDC),
                        "usd_price": str(PAID_PRICE_USDC),
                        "tx_hash": None,
                        "settlement_status": "unpaid_402" if blocked.status_code == 402 else "misconfigured",
                        "response_status": blocked.status_code,
                        "processing_ms": (time.perf_counter() - tpay) * 1000,
                        "is_real": False,
                    }
                )
            return blocked
        body = _read(request)
        text = str(body.get("text") or "")
        if not text.strip():
            raise HTTPException(400, "empty_text")
        schema = body.get("schema") if isinstance(body.get("schema"), dict) else None
        _guard_value({"text": text}, schema)
        result = reliable_json(text, schema)
        if payment_flags_on() and getattr(request.state, "x402_verified", None):
            receipt = settle_payment(request.state.x402_verified, getattr(request.state, "x402_payload", None), PAID_AJR)
            record_paid_call(
                {
                    "endpoint": "/v1/json/reliable",
                    "product_id": "json_reliable",
                    "payer": receipt.get("payer"),
                    "network": receipt.get("network") or X402_NETWORK,
                    "asset": receipt.get("asset") or "USDC",
                    "price": receipt.get("price") or str(PAID_PRICE_USDC),
                    "usd_price": receipt.get("price") or str(PAID_PRICE_USDC),
                    "amount_atomic": receipt.get("amount"),
                    "payTo": receipt.get("payTo"),
                    "tx_hash": receipt.get("tx_hash"),
                    "payment_hash": receipt.get("payment_hash"),
                    "nonce": receipt.get("nonce"),
                    "verify_status": receipt.get("verify_status"),
                    "settlement_status": receipt.get("settlement_status"),
                    "response_status": 200 if receipt.get("settlement_status") in {"settled", "mock_settled"} else 402,
                    "processing_ms": (time.perf_counter() - tpay) * 1000,
                    "is_real": bool(receipt.get("is_real")),
                }
            )
            if receipt.get("settlement_status") == "settled":
                resp = JSONResponse(result)
                resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
                return resp
            if receipt.get("settlement_status") == "mock_settled":
                resp = JSONResponse(result)
                resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
                resp.headers["X-AJR-SETTLEMENT"] = "MOCK_NOT_REAL"
                return resp
            return JSONResponse(
                {"error": "settlement_failed", "settlement_status": receipt.get("settlement_status"), "is_real": False},
                status_code=402,
            )
        return result

    @app.post("/v1/evidence/pack")
    async def evidence_pack(request: Request):
        tpay = time.perf_counter()
        blocked = maybe_payment_response(request, PAID_EVIDENCE)
        if blocked is not None:
            if evidence_payment_flags_on() and blocked.status_code != 402:
                record_paid_call(
                    {
                        "endpoint": PAID_EVIDENCE,
                        "product_id": "evidence_pack",
                        "payer": None,
                        "network": X402_NETWORK,
                        "asset": "USDC",
                        "price": str(EVIDENCE_PRICE_USDC),
                        "usd_price": str(EVIDENCE_PRICE_USDC),
                        "tx_hash": None,
                        "settlement_status": "unpaid_402" if blocked.status_code == 402 else "misconfigured",
                        "response_status": blocked.status_code,
                        "processing_ms": (time.perf_counter() - tpay) * 1000,
                        "is_real": False,
                    }
                )
            return blocked
        body = _read(request)
        try:
            pack = build_pack(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        failures = sum(1 for s in pack["sources"] if s.get("error"))
        ok = any(s.get("http_status") == 200 for s in pack["sources"]) and failures < len(pack["sources"])
        if not pack["sources"]:
            ok = False
        paid_ok = False
        if evidence_payment_flags_on() and getattr(request.state, "x402_verified", None):
            receipt = settle_payment(
                request.state.x402_verified, getattr(request.state, "x402_payload", None), PAID_EVIDENCE
            )
            record_paid_call(
                {
                    "endpoint": PAID_EVIDENCE,
                    "product_id": "evidence_pack",
                    "payer": receipt.get("payer"),
                    "network": receipt.get("network") or X402_NETWORK,
                    "asset": receipt.get("asset") or "USDC",
                    "price": receipt.get("price") or str(EVIDENCE_PRICE_USDC),
                    "usd_price": receipt.get("price") or str(EVIDENCE_PRICE_USDC),
                    "amount_atomic": receipt.get("amount"),
                    "payTo": receipt.get("payTo"),
                    "tx_hash": receipt.get("tx_hash"),
                    "payment_hash": receipt.get("payment_hash"),
                    "nonce": receipt.get("nonce"),
                    "verify_status": receipt.get("verify_status"),
                    "settlement_status": receipt.get("settlement_status"),
                    "response_status": 200 if receipt.get("settlement_status") in {"settled", "mock_settled"} else 402,
                    "processing_ms": (time.perf_counter() - tpay) * 1000,
                    "is_real": bool(receipt.get("is_real")),
                }
            )
            if receipt.get("settlement_status") == "settled":
                paid_ok = True
                resp = JSONResponse(pack)
                resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
                record_pack(
                    client_hash=getattr(request.state, "client_hash", None),
                    url_count=len(pack["sources"]),
                    success=bool(ok),
                    fetch_failures=failures,
                    http_status=200,
                    paid=True,
                )
                return resp
            if receipt.get("settlement_status") == "mock_settled":
                resp = JSONResponse(pack)
                resp.headers["PAYMENT-RESPONSE"] = encode_payment_response(receipt)
                resp.headers["X-AJR-SETTLEMENT"] = "MOCK_NOT_REAL"
                record_pack(
                    client_hash=getattr(request.state, "client_hash", None),
                    url_count=len(pack["sources"]),
                    success=bool(ok),
                    fetch_failures=failures,
                    http_status=200,
                    paid=False,
                )
                return resp
            return JSONResponse(
                {"error": "settlement_failed", "settlement_status": receipt.get("settlement_status"), "is_real": False},
                status_code=402,
            )
        record_pack(
            client_hash=getattr(request.state, "client_hash", None),
            url_count=len(pack["sources"]),
            success=bool(ok),
            fetch_failures=failures,
            http_status=200,
            paid=paid_ok,
        )
        return pack

    def _make_store_handler(prod: dict[str, Any]):
        async def handler(request: Request):
            tpay = time.perf_counter()
            path = prod["path"]
            blocked = maybe_payment_response(request, path)
            if blocked is not None:
                return blocked
            body = _read(request)
            try:
                result = run_product(prod["id"], body)
            except ValueError as e:
                record_product_event(
                    {
                        "product_id": prod["id"],
                        "endpoint": path,
                        "event": "processing_failure",
                        "is_real": str(getattr(request.state, "traffic_kind", ""))
                        not in {"SYNTHETIC_EXTERNAL_BUYER", "SYNTHETIC_BUYER"},
                        "http_status": 400,
                    }
                )
                raise HTTPException(400, str(e)) from e
            if payment_flags_on() and getattr(request.state, "x402_verified", None):
                return _finish_paid(request, path, result, tpay, prod["id"], str(prod["price_usdc"]))
            return result

        handler.__name__ = f"store_{prod['id']}"
        return handler

    for _prod in PRODUCTS:
        if _prod["id"] in {"json_reliable", "evidence_pack"}:
            continue
        app.add_api_route(_prod["path"], _make_store_handler(_prod), methods=["POST"])

    @app.post("/v1/json/reliable/batch", include_in_schema=bool(BATCH_PUBLIC))
    async def batch(request: Request):
        if not BATCH_PUBLIC:
            raise HTTPException(404, "batch_disabled_on_public_beta")
        body = _read(request)
        items = body.get("items")
        return reliable_batch(items if isinstance(items, list) else [], body.get("schema") if isinstance(body.get("schema"), dict) else None, MAX_BATCH)

    return app


app = create_json_beta_app()
