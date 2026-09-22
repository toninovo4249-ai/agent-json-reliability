"""Minimal robots.txt: do not fetch disallowed public paths."""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

UA_TOKEN = "FreshWebEvidencePack"


def _groups(text: str) -> list[dict]:
    groups: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if key == "user-agent":
            cur = {"agents": [val.lower()], "disallow": [], "allow": []}
            groups.append(cur)
        elif cur is None:
            continue
        elif key == "disallow":
            cur["disallow"].append(val)
        elif key == "allow":
            cur["allow"].append(val)
    return groups


def allowed_by_robots(robots_text: str | None, url: str, user_agent: str = UA_TOKEN) -> bool:
    if not robots_text:
        return True
    path = urlparse(url).path or "/"
    if urlparse(url).query:
        path = path + "?" + urlparse(url).query
    ua = user_agent.lower()
    groups = _groups(robots_text)
    matched = [g for g in groups if any(a == "*" or a in ua for a in g["agents"])]
    if not matched:
        return True

    def best(rules: list[str], kind: str) -> str:
        hits = [r for r in rules if r and path.startswith(r)]
        if not hits:
            return ""
        return max(hits, key=len)

    allow = ""
    disallow = ""
    for g in matched:
        a = best(g["allow"], "allow")
        d = best(g["disallow"], "disallow")
        if len(a) > len(allow):
            allow = a
        if len(d) > len(disallow):
            disallow = d
    if not disallow:
        return True
    if len(allow) > len(disallow):
        return True
    if len(allow) == len(disallow) and allow:
        return True
    return False


def robots_url_for(page_url: str) -> str:
    p = urlparse(page_url)
    return urljoin(f"{p.scheme}://{p.netloc}", "/robots.txt")
