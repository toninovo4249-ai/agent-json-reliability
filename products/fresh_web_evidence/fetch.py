"""Pinned public HTTP fetch. No bodies stored by caller metrics."""
from __future__ import annotations

import hashlib
import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urljoin

from products.fresh_web_evidence.robots import allowed_by_robots, robots_url_for
from products.fresh_web_evidence.ssrf import SsrfError, parse_public_http_url, resolve_public

MAX_URLS = 5
MAX_BYTES = 262144
TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 3
USER_AGENT = "FreshWebEvidencePack/0.1 (+https://github.com/toninovo4249-ai/agent-json-reliability)"
ALLOWED_CONTENT = (
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "application/ld+json",
    "text/plain",
    "text/xml",
    "application/xml",
)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, ip: str, port: int, timeout: float, context: ssl.SSLContext, server_hostname: str):
        super().__init__(ip, port=port, timeout=timeout, context=context)
        self._sni = server_hostname

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        ctx = getattr(self, "_context", None) or ssl.create_default_context()
        self.sock = ctx.wrap_socket(sock, server_hostname=self._sni)


@dataclass
class FetchResult:
    requested_url: str
    url: str
    fetched_at: str
    http_status: int | None = None
    content_sha256: str | None = None
    content_type: str | None = None
    title: str | None = None
    body: bytes = b""
    error: str | None = None
    robots_blocked: bool = False
    truncated: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ctype_ok(header: str | None) -> bool:
    if not header:
        return True
    base = header.split(";", 1)[0].strip().lower()
    if base in ALLOWED_CONTENT:
        return True
    return any(base.startswith(a) for a in ALLOWED_CONTENT)


def _read_limited(resp, max_bytes: int) -> tuple[bytes, bool]:
    chunks = []
    total = 0
    truncated = False
    while True:
        piece = resp.read(min(16384, max_bytes + 1 - total))
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            chunks.append(piece[: max(0, max_bytes - (total - len(piece)))])
            truncated = True
            break
        chunks.append(piece)
    return b"".join(chunks), truncated


def _request(url: str, timeout: float, max_bytes: int, method: str = "GET") -> tuple[int, dict[str, str], bytes, bool]:
    scheme, host, path, port, _ = parse_public_http_url(url)
    ips = resolve_public(host)
    ip = ips[0]
    ctx = ssl.create_default_context()
    if scheme == "https":
        conn: http.client.HTTPConnection = PinnedHTTPSConnection(ip, port, timeout, ctx, host)
    else:
        conn = http.client.HTTPConnection(ip, port=port, timeout=timeout)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host if port in (80, 443) else f"{host}:{port}")
        conn.putheader("User-Agent", USER_AGENT)
        conn.putheader("Accept", "text/html,application/json,application/ld+json,text/plain")
        conn.putheader("Accept-Encoding", "identity")
        conn.putheader("Connection", "close")
        conn.endheaders()
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        cl = headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_bytes and method == "GET":
            body, truncated = resp.read(max_bytes), True
        else:
            body, truncated = _read_limited(resp, max_bytes)
        return resp.status, headers, body, truncated
    finally:
        conn.close()


def fetch_url(
    url: str,
    *,
    timeout: float = TIMEOUT_SECONDS,
    max_bytes: int = MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    check_robots: bool = True,
    _transport: Callable | None = None,
) -> FetchResult:
    started = _now()
    transport = _transport or _request
    current = url.strip()
    hops = 0
    robots_cache: dict[str, str | None] = {}
    try:
        parse_public_http_url(current)
    except SsrfError as e:
        return FetchResult(requested_url=url, url=current, fetched_at=started, error=str(e), http_status=None)

    deadline = time.monotonic() + timeout
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            return FetchResult(requested_url=url, url=current, fetched_at=started, error="timeout", http_status=None)
        try:
            if check_robots:
                ru = robots_url_for(current)
                if ru not in robots_cache:
                    try:
                        st, _hd, body, _tr = transport(ru, min(remain, 3.0), 65536, "GET")
                        robots_cache[ru] = body.decode("utf-8", "replace") if st == 200 else None
                    except Exception:
                        robots_cache[ru] = None
                if not allowed_by_robots(robots_cache[ru], current):
                    return FetchResult(
                        requested_url=url,
                        url=current,
                        fetched_at=started,
                        error="robots_disallowed",
                        robots_blocked=True,
                        http_status=None,
                    )
            status, headers, body, truncated = transport(current, remain, max_bytes, "GET")
        except SsrfError as e:
            return FetchResult(requested_url=url, url=current, fetched_at=started, error=str(e))
        except TimeoutError:
            return FetchResult(requested_url=url, url=current, fetched_at=started, error="timeout")
        except OSError as e:
            msg = "timeout" if "timed out" in str(e).lower() else "fetch_failed"
            return FetchResult(requested_url=url, url=current, fetched_at=started, error=msg)
        except Exception:
            return FetchResult(requested_url=url, url=current, fetched_at=started, error="fetch_failed")

        if status in {301, 302, 303, 307, 308}:
            loc = headers.get("location")
            if not loc:
                return FetchResult(
                    requested_url=url, url=current, fetched_at=started, http_status=status, error="redirect_missing_location"
                )
            hops += 1
            if hops > max_redirects:
                return FetchResult(
                    requested_url=url, url=current, fetched_at=started, http_status=status, error="too_many_redirects"
                )
            nxt = urljoin(current, loc)
            try:
                parse_public_http_url(nxt)
            except SsrfError as e:
                return FetchResult(requested_url=url, url=nxt, fetched_at=started, error=str(e), http_status=status)
            current = nxt
            continue

        ctype = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if status == 200 and not _ctype_ok(headers.get("content-type")):
            return FetchResult(
                requested_url=url,
                url=current,
                fetched_at=started,
                http_status=status,
                content_type=headers.get("content-type"),
                content_sha256=hashlib.sha256(body).hexdigest() if body else None,
                error="unsupported_content_type",
                truncated=truncated,
            )
        sha = hashlib.sha256(body).hexdigest() if body else hashlib.sha256(b"").hexdigest()
        return FetchResult(
            requested_url=url,
            url=current,
            fetched_at=_now(),
            http_status=status,
            content_sha256=sha,
            content_type=headers.get("content-type"),
            body=body if status == 200 else b"",
            truncated=truncated,
            error=None if status == 200 else f"http_{status}",
        )
