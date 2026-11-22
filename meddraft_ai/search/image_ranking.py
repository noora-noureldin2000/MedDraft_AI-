"""Keyword and metadata ranking for image-search results.

Adapted from the scoring model in glebis/claude-skills ``google-image-search``:
required terms, optional terms, excluded terms, preferred hosts, MIME type, and
resolution. The goal is to keep a short, relevant result set for an LLM context
window without a second LLM call.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Mapping, Sequence

IMAGE_SCORE_WEIGHTS: dict[str, int] = {
    "required_all_present": 30,
    "required_missing": -80,
    "optional_match": 5,
    "exclude_match": -50,
    "preferred_host": 25,
    "unknown_host": -5,
    "good_mime": 5,
    "gif_mime": -10,
    "high_resolution": 10,
    "low_resolution": -10,
}

_GOOD_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".avif")
_LOW_IMAGE_SUFFIXES = (".gif", ".svg", ".ico")


def normalise_terms(values: str | Sequence[str] | None) -> list[str]:
    if values is None:
        return []
    parts = values.split(",") if isinstance(values, str) else list(values)
    return [str(part).strip().lower() for part in parts if str(part).strip()]


def _result_text(item: Mapping[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("title", "image_url", "context_url", "thumbnail_url", "provider")
    ).lower()


def _result_host(item: Mapping[str, Any]) -> str:
    for key in ("context_url", "image_url"):
        try:
            host = urllib.parse.urlsplit(str(item.get(key) or "")).netloc.lower()
        except ValueError:
            host = ""
        if host:
            return host[4:] if host.startswith("www.") else host
    return ""


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
        return number if number > 0 else 0
    except (TypeError, ValueError):
        return 0


def score_image_result(
    item: Mapping[str, Any],
    *,
    required_terms: Sequence[str] = (),
    optional_terms: Sequence[str] = (),
    exclude_terms: Sequence[str] = (),
    preferred_hosts: Sequence[str] = (),
) -> tuple[float, list[str]]:
    """Score one result against keyword, host, MIME, and resolution signals."""
    haystack = _result_text(item)
    image_url = str(item.get("image_url") or "").lower().split("?", 1)[0]
    width = _positive_int(item.get("width"))
    height = _positive_int(item.get("height"))

    score = 0.0
    reasons: list[str] = []

    if required_terms:
        missing = [term for term in required_terms if term not in haystack]
        if missing:
            score += IMAGE_SCORE_WEIGHTS["required_missing"]
            reasons.append("missing required: " + ", ".join(missing[:3]))
        else:
            score += IMAGE_SCORE_WEIGHTS["required_all_present"]
            reasons.append("all required terms present")

    for term in optional_terms:
        if term in haystack:
            score += IMAGE_SCORE_WEIGHTS["optional_match"]
            reasons.append(f"optional match: {term}")

    for term in exclude_terms:
        if term in haystack:
            score += IMAGE_SCORE_WEIGHTS["exclude_match"]
            reasons.append(f"excluded term: {term}")

    host = _result_host(item)
    hosts = [h.lower().strip().removeprefix("www.") for h in preferred_hosts if h.strip()]
    if hosts:
        if any(host == h or host.endswith("." + h) for h in hosts):
            score += IMAGE_SCORE_WEIGHTS["preferred_host"]
            reasons.append(f"preferred host: {host}")
        else:
            score += IMAGE_SCORE_WEIGHTS["unknown_host"]

    if image_url.endswith(_GOOD_IMAGE_SUFFIXES):
        score += IMAGE_SCORE_WEIGHTS["good_mime"]
    elif image_url.endswith(_LOW_IMAGE_SUFFIXES):
        score += IMAGE_SCORE_WEIGHTS["gif_mime"]

    if width and height:
        if width * height >= 250_000:
            score += IMAGE_SCORE_WEIGHTS["high_resolution"]
        elif width <= 160 or height <= 120:
            score += IMAGE_SCORE_WEIGHTS["low_resolution"]

    return score, reasons


def filter_and_rank_results(
    results: Sequence[Mapping[str, Any]],
    *,
    required_terms: Sequence[str] = (),
    optional_terms: Sequence[str] = (),
    exclude_terms: Sequence[str] = (),
    preferred_hosts: Sequence[str] = (),
    hard_exclude: bool = True,
) -> list[dict[str, Any]]:
    """Drop hard-excluded images, attach a score, and rank best-first."""
    ranked: list[dict[str, Any]] = []
    for result in results:
        haystack = _result_text(result)
        if hard_exclude and any(term in haystack for term in exclude_terms):
            continue
        score, reasons = score_image_result(
            result,
            required_terms=required_terms,
            optional_terms=optional_terms,
            exclude_terms=exclude_terms,
            preferred_hosts=preferred_hosts,
        )
        enriched = dict(result)
        enriched["relevance_score"] = round(score, 2)
        if reasons:
            enriched["relevance_reasons"] = reasons[:4]
        ranked.append(enriched)
    return sorted(ranked, key=lambda entry: entry.get("relevance_score", 0), reverse=True)


__all__ = [
    "IMAGE_SCORE_WEIGHTS",
    "normalise_terms",
    "score_image_result",
    "filter_and_rank_results",
]
