"""Deterministic HTML/JSON claim extraction. No LLM."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

from products.fresh_web_evidence.fetch import FetchResult


class _Dom(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self._in_title = False
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.ld_chunks: list[str] = []
        self._in_ld = False
        self._ld_buf: list[str] = []
        self._ld_type = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            self.metas.append(ad)
        if tag == "link":
            self.links.append(ad)
        if tag == "script" and "ld+json" in (ad.get("type") or "").lower():
            self._in_ld = True
            self._ld_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld_chunks.append("".join(self._ld_buf))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_ld:
            self._ld_buf.append(data)


def _norm(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _ld_facts(obj: Any, prefix: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(obj, list):
        for i, item in enumerate(obj[:20]):
            out.extend(_ld_facts(item, f"{prefix}[{i}]"))
        return out
    if not isinstance(obj, dict):
        if _norm(obj):
            out.append({"key": prefix, "value": _norm(obj)})
        return out
    interesting = (
        "name",
        "headline",
        "title",
        "price",
        "lowprice",
        "highprice",
        "pricecurrency",
        "sku",
        "gtin",
        "datepublished",
        "datemodified",
        "datecreated",
        "availability",
        "version",
        "identifier",
    )
    for k, v in obj.items():
        lk = str(k).lower()
        path = f"{prefix}.{k}" if prefix else str(k)
        if lk == "@graph":
            out.extend(_ld_facts(v, prefix))
            continue
        if lk == "offers":
            out.extend(_ld_facts(v, path))
            continue
        if lk in interesting or lk in {"name", "price"}:
            if isinstance(v, (dict, list)):
                out.extend(_ld_facts(v, path))
            else:
                nv = _norm(v)
                if nv:
                    out.append({"key": path, "value": nv})
    return out


def extract_claims(fr: FetchResult, source_index: int) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    if fr.error or fr.http_status != 200 or not fr.body:
        return claims
    ctype = (fr.content_type or "").lower()
    body = fr.body

    def add(key: str, value: str) -> None:
        v = _norm(value)
        if not v:
            return
        claims.append(
            {
                "key": key,
                "value": v,
                "source_index": source_index,
                "source_url": fr.url,
            }
        )

    if "json" in ctype and "html" not in ctype:
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return claims
        if isinstance(data, dict):
            for k, v in list(data.items())[:50]:
                if isinstance(v, (str, int, float, bool)) or v is None:
                    add(f"json.{k}", _norm(v))
        return claims

    text = body.decode("utf-8", "replace")
    dom = _Dom()
    try:
        dom.feed(text)
        dom.close()
    except Exception:
        pass
    title = _norm("".join(dom.title_parts))
    if title:
        add("html.title", title)
        fr.title = title
    for m in dom.metas:
        name = (m.get("name") or m.get("property") or m.get("itemprop") or "").lower()
        content = m.get("content") or ""
        if name in {"description", "og:title", "og:description", "og:url", "og:site_name", "article:published_time"}:
            add(f"meta.{name}", content)
    for ln in dom.links:
        if (ln.get("rel") or "").lower() == "canonical" and ln.get("href"):
            add("link.canonical", ln["href"])
    for chunk in dom.ld_chunks[:10]:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        for item in _ld_facts(data, "jsonld"):
            add(item["key"], item["value"])
    return claims


def facts_from_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for c in claims:
        k = (c["key"], c["value"])
        rec = grouped.setdefault(
            k,
            {"key": c["key"], "value": c["value"], "text": f"{c['key']}={c['value']}", "source_indexes": [], "source_urls": []},
        )
        if c["source_index"] not in rec["source_indexes"]:
            rec["source_indexes"].append(c["source_index"])
            rec["source_urls"].append(c["source_url"])
    facts = list(grouped.values())
    facts.sort(key=lambda x: (x["key"], x["value"]))
    return facts
