"""Assemble a Fresh Web Evidence Pack. Always fetches at request time."""
from __future__ import annotations

from typing import Any, Callable

from products.fresh_web_evidence.contradict import find_contradictions
from products.fresh_web_evidence.extract import extract_claims, facts_from_claims
from products.fresh_web_evidence.fetch import MAX_URLS, FetchResult, fetch_url


def normalize_urls(payload: dict[str, Any]) -> list[str]:
    if payload.get("urls") is not None:
        raw = payload.get("urls")
        if not isinstance(raw, list):
            raise ValueError("urls_must_be_array")
        urls = [str(u).strip() for u in raw if str(u).strip()]
    elif payload.get("url"):
        urls = [str(payload.get("url")).strip()]
    else:
        raise ValueError("url_or_urls_required")
    if len(urls) > MAX_URLS:
        raise ValueError("too_many_urls")
    if not urls:
        raise ValueError("url_or_urls_required")
    return urls


def _confidence(sources: list[dict[str, Any]], contradictions: list, fetch_failures: int) -> float:
    ok = sum(1 for s in sources if s.get("http_status") == 200 and not s.get("error"))
    n = len(sources) or 1
    base = 0.35 + 0.2 * ok
    if ok >= 2 and not contradictions:
        base += 0.25
    if contradictions:
        base -= 0.2
    if fetch_failures:
        base -= 0.1 * fetch_failures
    return round(max(0.05, min(0.95, base / max(1, 0.5 + 0.15 * n) * (0.55 + 0.15 * ok))), 2)


def build_pack(payload: dict[str, Any], *, fetch_fn: Callable[[str], FetchResult] | None = None) -> dict[str, Any]:
    urls = normalize_urls(payload)
    fetch_fn = fetch_fn or fetch_url
    results: list[FetchResult] = []
    warnings: list[str] = []
    for u in urls:
        fr = fetch_fn(u)
        results.append(fr)
        if fr.robots_blocked:
            warnings.append(f"robots_disallowed:{u}")
        if fr.truncated:
            warnings.append(f"truncated:{fr.url}")
        if fr.error:
            warnings.append(f"fetch_error:{fr.error}:{u}")

    claims: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    failures = 0
    for i, fr in enumerate(results):
        src = {
            "url": fr.url,
            "requested_url": fr.requested_url,
            "fetched_at": fr.fetched_at,
            "http_status": fr.http_status,
            "content_sha256": fr.content_sha256,
            "content_type": fr.content_type,
            "title": fr.title,
        }
        if fr.error:
            src["error"] = fr.error
            failures += 1
        sources.append(src)
        claims.extend(extract_claims(fr, i))
        if not src.get("title") and fr.title:
            src["title"] = fr.title

    facts = facts_from_claims(claims)
    for f in facts:
        if not f.get("source_indexes"):
            warnings.append("fact_missing_provenance")
    contradictions = find_contradictions(claims)
    conf = _confidence(sources, contradictions, failures)
    if contradictions:
        warnings.append("contradictions_present")
    return {
        "facts": facts,
        "sources": sources,
        "contradictions": contradictions,
        "confidence": conf,
        "warnings": warnings,
        "llm_used": False,
        "paid_upstream_used": False,
        "fresh_fetch": True,
    }
