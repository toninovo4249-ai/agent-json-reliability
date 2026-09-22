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
from products.beta.landing import agents_md, landing_html, llms_txt, robots_txt
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
    PAID_PRICE_USDC,
    PAID_ROUTE_ENABLED,
    PAYMENT_REQUIRED,
    PUBLIC_BETA_CONFIRM,
    PUBLIC_PATHS,
    X402_NETWORK,
    X402_PAYMENT_ENABLED,
    current_base_url,
    public_exposure_mode,
)
from products.beta.paid_ledger import record_paid_call
from products.beta.store import record_v16
from products.beta.x402_gate import (
    encode_payment_response,
    maybe_payment_response,
    payment_flags_on,
    settle_payment,
)
from products.gateway.mcp_server import handle_rpc
from products.gateway.rate_limit import RateLimiter

ALLOWED_PREFIX = ("/v1/json/", "/.well-known/")


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
        kind = traffic_kind(request.headers, ua, request.client.host if request.client else None, path)
        ctype, conf = ua_coarse(ua)
        ch = client_hash(request.client.host if request.client else None, ua)
        src = request.query_params.get("source")
        if path.startswith("/v1/json"):
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
        try:
            body = await request.body()
        except Exception:
            body = b""
        if len(body) > MAX_REQUEST_BODY_BYTES:
            if path.startswith("/v1/json"):
                sem.release()
            return JSONResponse({"error": "payload too large", "error_class": "oversized"}, status_code=413)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = StarletteRequest(request.scope, receive)
        request.state.body = body
        request.state.traffic_kind = kind
        request.state.client_hash = ch
        try:
            resp = await call_next(request)
        finally:
            if path.startswith("/v1/json"):
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
            "/AGENTS.md",
            "/robots.txt",
            "/mcp",
        } else None
        probe = None
        if resp.status_code == 404 and path not in PUBLIC_PATHS and not path.startswith("/v1/json"):
            probe = "RANDOM_PROBE"
            if kind == "REAL_EXTERNAL_UNKNOWN":
                kind = "RANDOM_PROBE"
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


def create_json_beta_app() -> FastAPI:
    limiter = RateLimiter(per_minute=MAX_REQUESTS_PER_MINUTE_PER_SESSION, burst=max(5, MAX_REQUESTS_PER_MINUTE_PER_SESSION // 3))
    sem = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
    app = FastAPI(
        title="Agent JSON Reliability free beta",
        version=BETA_VERSION,
        description="FREE BETA. NO PAYMENT REQUIRED. Not a paid x402 endpoint.",
        servers=[{"url": current_base_url(), "description": "PUBLIC_BASE_URL"}],
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
        schema["servers"] = [{"url": current_base_url(), "description": "PUBLIC_BASE_URL"}]
        schema["info"]["x-free-beta"] = True
        schema["info"]["x-payment-required"] = False
        schema["info"]["x-llm-required"] = False
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
            "x402_payment_integrated": False,
            "X402_PAYMENT_ENABLED": X402_PAYMENT_ENABLED,
            "PAID_ROUTE_ENABLED": PAID_ROUTE_ENABLED,
            "FIRST_PAID_BUYER_MODE": FIRST_PAID_BUYER_MODE,
            "x402_middleware_present": True,
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
            "tools": [s["tool_name"] for s in public_catalog()["services"]],
            "html_exposed": ENABLE_HTML_BETA,
        }

    @app.get("/.well-known/agent-services.json")
    def manifest():
        return public_catalog()

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return robots_txt()

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms():
        return llms_txt()

    @app.get("/AGENTS.md", response_class=PlainTextResponse)
    def agents():
        return agents_md()

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
            if payment_flags_on():
                record_paid_call(
                    {
                        "endpoint": "/v1/json/reliable",
                        "payer": None,
                        "network": X402_NETWORK,
                        "asset": "USDC",
                        "price": str(PAID_PRICE_USDC),
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
            receipt = settle_payment(request.state.x402_verified, getattr(request.state, "x402_payload", None))
            record_paid_call(
                {
                    "endpoint": "/v1/json/reliable",
                    "payer": receipt.get("payer"),
                    "network": receipt.get("network") or X402_NETWORK,
                    "asset": receipt.get("asset") or "USDC",
                    "price": receipt.get("price") or str(PAID_PRICE_USDC),
                    "amount_atomic": receipt.get("amount"),
                    "tx_hash": receipt.get("tx_hash"),
                    "payment_hash": receipt.get("payment_hash"),
                    "nonce": receipt.get("nonce"),
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

    @app.post("/v1/json/reliable/batch")
    async def batch(request: Request):
        if not BATCH_PUBLIC:
            raise HTTPException(404, "batch_disabled_on_public_beta")
        body = _read(request)
        items = body.get("items")
        return reliable_batch(items if isinstance(items, list) else [], body.get("schema") if isinstance(body.get("schema"), dict) else None, MAX_BATCH)

    return app


app = create_json_beta_app()
