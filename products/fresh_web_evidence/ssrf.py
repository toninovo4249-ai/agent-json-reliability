"""SSRF guards: public http(s) only, no private/metadata/loopback."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, None}

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:127.0.0.0/104"),
    ipaddress.ip_network("::ffff:10.0.0.0/104"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
    ipaddress.ip_network("::ffff:172.16.0.0/108"),
    ipaddress.ip_network("::ffff:192.168.0.0/112"),
]

BLOCKED_HOST_EXACT = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
}


class SsrfError(Exception):
    pass


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    if ip.is_unspecified:
        return True
    for net in BLOCKED_NETWORKS:
        try:
            if ip in net:
                return True
        except Exception:
            continue
    return False


def host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").strip().lower()


def parse_public_http_url(url: str) -> tuple[str, str, str, int, str]:
    if not isinstance(url, str) or not url.strip():
        raise SsrfError("invalid_url")
    raw = url.strip()
    if "\\" in raw or raw.lower().startswith("file:") or "\n" in raw or "\r" in raw:
        raise SsrfError("invalid_url")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SsrfError("non_http_scheme")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SsrfError("invalid_url")
    if host in BLOCKED_HOST_EXACT or host.endswith(".localhost") or host.endswith(".internal"):
        raise SsrfError("blocked_host")
    if parsed.username or parsed.password:
        raise SsrfError("userinfo_forbidden")
    port = parsed.port
    if port not in ALLOWED_PORTS:
        raise SsrfError("blocked_port")
    if port is None:
        port = 443 if scheme == "https" else 80
    path = parsed.path or "/"
    if parsed.query:
        path = path + "?" + parsed.query
    try:
        ip = ipaddress.ip_address(host)
        if _ip_blocked(ip):
            raise SsrfError("blocked_ip")
    except ValueError:
        pass
    return scheme, host, path, port, raw


def resolve_public(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SsrfError("dns_failed") from e
    addrs: list[str] = []
    for info in infos:
        ip_s = info[4][0]
        ip = ipaddress.ip_address(ip_s)
        if _ip_blocked(ip):
            raise SsrfError("blocked_ip")
        if ip_s not in addrs:
            addrs.append(ip_s)
    if not addrs:
        raise SsrfError("dns_failed")
    return addrs
