"""Provider-chained Google Images search with free-tier quota tracking.

Search order (first configured, non-exhausted provider wins):

1. ``serpapi``    — SerpApi Google Images (100 searches/month free)
2. ``brave``      — Brave Images API (2,000 queries/month free)
3. ``browser``    — Playwright Google Images scrape (no API key, last resort)

``google_cse`` (Google Custom Search JSON API) is still supported for
grandfathered projects, but Google closed the API to new customers and will
stop serving existing customers on 2027-01-01. It is therefore excluded from
the default chain; add it explicitly with ``IMAGE_SEARCH_PROVIDER_ORDER`` if
your project already had access before the closure.

A small JSON ledger (``.cache/image_search_quota.json``) records local usage so
the chain stops spending an exhausted free tier and falls through to the next
provider. The ledger is best-effort: it cannot see usage from other machines or
other tools sharing the same API key.

Every public entry point returns a JSON-serialisable envelope. Provider,
network, quota, and browser failures never raise; they are reported in
``attempts`` so the calling agent can explain what happened.

No key is ever returned by ``get_provider_status`` or written to an envelope.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from meddraft_ai.core.config import get_config
from meddraft_ai.search.image_quota import FREE_TIER_LIMITS, QuotaLedger
from meddraft_ai.search.image_ranking import (
    filter_and_rank_results,
    normalise_terms,
)

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
BRAVE_IMAGES_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"

DEFAULT_PROVIDER_ORDER = ("serpapi", "brave", "browser")
MAX_RESULTS = 10  # Google CSE accepts at most 10 results per request.

PROVIDER_LABELS: dict[str, str] = {
    "serpapi": "SerpApi Google Images",
    "google_cse": "Google Custom Search JSON API (legacy)",
    "brave": "Brave Images API",
    "browser": "Playwright Google Images (no key)",
}

PROVIDER_ALIASES: dict[str, str] = {
    "serp": "serpapi",
    "serpapi": "serpapi",
    "serp_api": "serpapi",
    "google": "google_cse",
    "googlecse": "google_cse",
    "google_cse": "google_cse",
    "google-cse": "google_cse",
    "cse": "google_cse",
    "google_custom_search": "google_cse",
    "brave": "brave",
    "brave_images": "brave",
    "browser": "browser",
    "playwright": "browser",
    "playwright_mcp": "browser",
}


class ProviderRequestError(Exception):
    """A provider call failed in a way the fallback chain should report."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


def _extract_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        detail = str(error.get("detail") or "")
        meta = error.get("meta") if isinstance(error.get("meta"), dict) else {}
        nested = meta.get("errors") if isinstance(meta.get("errors"), list) else []
        if nested and isinstance(nested[0], dict):
            location = ".".join(str(part) for part in nested[0].get("loc", []))
            message = nested[0].get("msg") or ""
            if message:
                return f"{detail}: {location} {message}".strip(": ")
        return str(error.get("message") or detail or error.get("status") or "")
    if isinstance(error, str):
        return error
    for key in ("message", "detail", "error_description"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _redact_secrets(text: str, secrets: Sequence[str] = ()) -> str:
    if not text:
        return ""
    values = list(secrets)
    for name in (
        "SERP_API_KEY",
        "SERPAPI_API_KEY",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "BRAVE_API_KEY",
        "BRAVE_SEARCH_API_KEY",
    ):
        value = os.getenv(name, "")
        if value:
            values.append(value)
    for value in values:
        if value and len(str(value)) >= 8:
            text = text.replace(str(value), "***")
    return text


def _parse_retry_after(headers: Any) -> float | None:
    if not headers:
        return None
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if not raw:
        return None
    try:
        return max(1.0, float(str(raw).strip()))
    except ValueError:
        return None


def _http_get_json(
    url: str,
    params: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 20,
    secrets: Sequence[str] = (),
) -> Any:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query}"
    request = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "MedDraft_AI/1.0 (image search)",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            **dict(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", "replace")
        payload = _safe_json(error_body)
        message = (
            _extract_error_message(payload)
            or error_body[:300]
            or f"HTTP {exc.code}"
        )
        raise ProviderRequestError(
            _redact_secrets(message, secrets),
            status=exc.code,
            retry_after=_parse_retry_after(getattr(exc, "headers", None)),
        ) from None
    except Exception as exc:  # URLError, timeout, socket errors
        raise ProviderRequestError(
            _redact_secrets(f"network error: {exc}", secrets),
        ) from None

    payload = _safe_json(body)
    if not payload:
        raise ProviderRequestError("provider returned a non-JSON response")
    return payload


def _looks_like_quota_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(
        token in lowered
        for token in (
            "quota",
            "rate limit",
            "ratelimit",
            "exceeded",
            "limit reached",
            "too many requests",
            "insufficient",
            "credit",
        )
    )


def _canonical_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(str(url).strip())
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
    )


def _as_int(value: Any) -> int | None:
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _normalise_item(
    *,
    title: Any,
    image_url: Any,
    thumbnail_url: Any = None,
    context_url: Any = None,
    width: Any = None,
    height: Any = None,
    provider: str,
    position: int,
) -> dict[str, Any] | None:
    canonical = _canonical_url(str(image_url or ""))
    if not canonical:
        return None
    context = _canonical_url(str(context_url or "")) or None
    thumbnail = _canonical_url(str(thumbnail_url or "")) or None
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip() or f"Image {position}"
    if len(clean_title) > 160:
        clean_title = clean_title[:157].rstrip() + "..."
    return {
        "title": clean_title,
        "image_url": canonical,
        "thumbnail_url": thumbnail,
        "context_url": context,
        "width": _as_int(width),
        "height": _as_int(height),
        "provider": provider,
        "position": position,
    }


def _dedupe(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in results:
        key = _canonical_url(str(item.get("image_url", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(dict(item))
    return unique


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def _search_serpapi(
    query: str,
    num_results: int,
    *,
    api_key: str,
    safe_search: str = "active",
    timeout: float = 20,
) -> list[dict[str, Any]]:
    """Google Images via SerpApi. ``original`` is the full-size image."""
    payload = _http_get_json(
        SERPAPI_ENDPOINT,
        {
            "engine": "google_images",
            "q": query,
            "api_key": api_key,
            "num": min(num_results, 100),
            "hl": "en",
            "safe": "active" if safe_search == "active" else "off",
        },
        timeout=timeout,
        secrets=(api_key,),
    )
    if payload.get("error"):
        raise ProviderRequestError(
            _redact_secrets(str(payload["error"]), (api_key,)),
            status=429 if _looks_like_quota_error(str(payload["error"])) else None,
        )

    results: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("images_results") or [], start=1):
        if len(results) >= num_results:
            break
        if not isinstance(item, dict):
            continue
        normalised = _normalise_item(
            title=item.get("title"),
            image_url=item.get("original") or item.get("thumbnail"),
            thumbnail_url=item.get("thumbnail"),
            context_url=item.get("link"),
            width=item.get("original_width"),
            height=item.get("original_height"),
            provider="serpapi",
            position=index,
        )
        if normalised:
            results.append(normalised)
    return results


def _search_google_cse(
    query: str,
    num_results: int,
    *,
    api_key: str,
    cse_id: str,
    safe_search: str = "active",
    timeout: float = 20,
) -> list[dict[str, Any]]:
    """Google Images via the official Custom Search JSON API."""
    payload = _http_get_json(
        GOOGLE_CSE_ENDPOINT,
        {
            "q": query,
            "cx": cse_id,
            "key": api_key,
            "searchType": "image",
            "num": min(num_results, 10),
            "safe": "active" if safe_search == "active" else "off",
        },
        timeout=timeout,
        secrets=(api_key,),
    )
    if payload.get("error"):
        message = _extract_error_message(payload) or "Google Custom Search error"
        raise ProviderRequestError(
            _redact_secrets(message, (api_key,)),
            status=403 if _looks_like_quota_error(message) else None,
        )

    results: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("items") or [], start=1):
        if len(results) >= num_results:
            break
        if not isinstance(item, dict):
            continue
        image = item.get("image") if isinstance(item.get("image"), dict) else {}
        normalised = _normalise_item(
            title=item.get("title"),
            image_url=item.get("link"),
            thumbnail_url=image.get("thumbnailLink"),
            context_url=image.get("contextLink"),
            width=image.get("width"),
            height=image.get("height"),
            provider="google_cse",
            position=index,
        )
        if normalised:
            results.append(normalised)
    return results


def _search_brave(
    query: str,
    num_results: int,
    *,
    api_key: str,
    safe_search: str = "active",
    timeout: float = 20,
) -> list[dict[str, Any]]:
    """Brave Images API. ``properties.url`` is the image; ``url`` is the page."""
    payload = _http_get_json(
        BRAVE_IMAGES_ENDPOINT,
        {
            "q": query,
            "count": min(num_results, 200),
            "safesearch": "strict" if safe_search == "active" else "off",
            "search_lang": "en",
        },
        headers={"X-Subscription-Token": api_key},
        timeout=timeout,
        secrets=(api_key,),
    )

    results: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("results") or [], start=1):
        if len(results) >= num_results:
            break
        if not isinstance(item, dict):
            continue
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        thumbnail = item.get("thumbnail") if isinstance(item.get("thumbnail"), dict) else {}
        image_url = properties.get("url") or item.get("url")
        page_url = item.get("url")
        normalised = _normalise_item(
            title=item.get("title"),
            image_url=image_url,
            thumbnail_url=thumbnail.get("src"),
            context_url=page_url if page_url != image_url else None,
            width=properties.get("width"),
            height=properties.get("height"),
            provider="brave",
            position=index,
        )
        if normalised:
            results.append(normalised)
    return results


def _browser_cli_path() -> Path:
    return Path(__file__).parent / "browser_engine" / "dist" / "cli.js"


def _browser_available() -> bool:
    return bool(shutil.which("node")) and _browser_cli_path().exists()


def _parse_browser_payload(payload: Mapping[str, Any], num_results: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("results") or [], start=1):
        if len(results) >= num_results:
            break
        if not isinstance(item, dict):
            continue
        normalised = _normalise_item(
            title=item.get("title"),
            image_url=item.get("imageUrl") or item.get("image_url") or item.get("original"),
            thumbnail_url=item.get("thumbnailUrl") or item.get("thumbnail_url"),
            context_url=item.get("contextUrl") or item.get("context_url"),
            width=item.get("width"),
            height=item.get("height"),
            provider="browser",
            position=index,
        )
        if normalised:
            results.append(normalised)
    return results


def _search_browser(
    query: str,
    num_results: int,
    *,
    timeout: float = 150,
    screenshot_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Google Images via the bundled Playwright engine (emergency fallback)."""
    if not _browser_available():
        raise ProviderRequestError(
            "Playwright browser engine unavailable: install Node.js and run "
            "`npm run build` in meddraft_ai/search/browser_engine."
        )

    config = get_config()
    command = [
        "node",
        str(_browser_cli_path()),
        "image-search",
        query,
        str(min(num_results, MAX_RESULTS)),
    ]
    if screenshot_path is not None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        command.append(str(screenshot_path))

    env = os.environ.copy()
    env["BROWSER_HEADLESS"] = "true" if config.BROWSER_HEADLESS else "false"
    if config.BROWSER_PROXY_SERVER:
        env["PROXY_SERVER"] = config.BROWSER_PROXY_SERVER
    if config.BROWSER_PROXY_USERNAME:
        env["PROXY_USERNAME"] = config.BROWSER_PROXY_USERNAME
    if config.BROWSER_PROXY_PASSWORD:
        env["PROXY_PASSWORD"] = config.BROWSER_PROXY_PASSWORD

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ProviderRequestError(f"browser search timed out after {int(timeout)}s") from None
    except OSError as exc:
        raise ProviderRequestError(f"could not start browser engine: {exc}") from None

    if completed.returncode != 0:
        for line in reversed((completed.stderr or "").strip().splitlines()):
            if line.startswith("{") and line.endswith("}"):
                payload = _safe_json(line)
                if isinstance(payload, dict) and payload.get("error"):
                    raise ProviderRequestError(str(payload["error"])[:400])
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise ProviderRequestError(detail[-1][:400] if detail else "browser engine failed")

    payload: Mapping[str, Any] | None = None
    for line in reversed((completed.stdout or "").strip().splitlines()):
        if line.startswith("{") and line.endswith("}"):
            candidate = _safe_json(line)
            if isinstance(candidate, dict):
                payload = candidate
                break
    if payload is None:
        raise ProviderRequestError("browser engine returned no JSON payload")
    if not payload.get("success"):
        raise ProviderRequestError(str(payload.get("error") or "browser search failed"))

    saved = payload.get("screenshot")
    saved_path = str(saved) if saved else (str(screenshot_path) if screenshot_path else None)
    return _parse_browser_payload(payload, num_results), saved_path


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def resolve_provider_order(provider_order: str | Sequence[str] | None = None) -> list[str]:
    """Normalise an order list; unknown names are ignored, duplicates removed."""
    if provider_order is None:
        provider_order = os.getenv("IMAGE_SEARCH_PROVIDER_ORDER") or getattr(
            get_config(), "IMAGE_SEARCH_PROVIDER_ORDER", ""
        )
    parts = (
        [part.strip() for part in provider_order.split(",")]
        if isinstance(provider_order, str)
        else [str(part).strip() for part in provider_order]
    )
    order: list[str] = []
    for part in parts:
        if not part:
            continue
        key = PROVIDER_ALIASES.get(part.lower().replace(" ", "_"))
        if key and key not in order:
            order.append(key)
    return order or list(DEFAULT_PROVIDER_ORDER)


def _resolve_credentials(provider: str) -> tuple[bool, dict[str, str], str]:
    """Return ``(configured, values, missing_hint)`` without exposing secrets."""
    config = get_config()
    if provider == "serpapi":
        key = (
            os.getenv("SERP_API_KEY")
            or os.getenv("SERPAPI_API_KEY")
            or getattr(config, "SERP_API_KEY", "")
        ).strip()
        return bool(key), {"api_key": key}, "SERP_API_KEY"
    if provider == "google_cse":
        key = (
            os.getenv("GOOGLE_CSE_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or getattr(config, "GOOGLE_CSE_API_KEY", "")
        ).strip()
        cse_id = (
            os.getenv("GOOGLE_CSE_ID")
            or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
            or os.getenv("GOOGLE_CX")
            or os.getenv("Search engine ID")
            or getattr(config, "GOOGLE_CSE_ID", "")
        ).strip()
        configured = bool(key and cse_id)
        return configured, {"api_key": key, "cse_id": cse_id}, "GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID"
    if provider == "brave":
        key = (
            os.getenv("BRAVE_API_KEY")
            or os.getenv("BRAVE_SEARCH_API_KEY")
            or getattr(config, "BRAVE_API_KEY", "")
        ).strip()
        return bool(key), {"api_key": key}, "BRAVE_API_KEY"
    if provider == "browser":
        return _browser_available(), {}, "Node.js + meddraft_ai/search/browser_engine/dist/cli.js"
    return False, {}, f"unknown provider {provider!r}"


def get_provider_status(ledger: QuotaLedger | None = None) -> list[dict[str, Any]]:
    """Configuration and remaining quota for every provider. Never returns keys."""
    config = get_config()
    ledger = ledger or QuotaLedger(
        getattr(config, "IMAGE_SEARCH_QUOTA_FILE", None),
        enabled=bool(getattr(config, "IMAGE_SEARCH_QUOTA_ENABLED", True)),
    )
    statuses: list[dict[str, Any]] = []
    for provider, label in PROVIDER_LABELS.items():
        configured, _, hint = _resolve_credentials(provider)
        statuses.append(
            {
                "provider": provider,
                "label": label,
                "configured": configured,
                "missing": None if configured else hint,
                "legacy": provider == "google_cse",
                "free_tier": FREE_TIER_LIMITS[provider]["note"],
                "quota": ledger.status(provider),
            }
        )
    return statuses


# ---------------------------------------------------------------------------
# Search chain
# ---------------------------------------------------------------------------


def _screenshot_target(configured_path: str | Path | None) -> Path | None:
    if configured_path is None:
        return None
    if str(configured_path).strip().lower() in ("", "auto"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return get_config().OUTPUT_DIR / "image_search" / f"google_images_{stamp}.png"
    return Path(configured_path)


@dataclass
class _SearchContext:
    query: str
    requested: int
    safe_search: str
    api_timeout: float
    browser_timeout: float
    screenshot_target: Path | None
    ledger: QuotaLedger
    required: list[str]
    optional: list[str]
    excluded: list[str]
    hosts: list[str]

    @property
    def ranking_active(self) -> bool:
        return bool(self.required or self.optional or self.excluded or self.hosts)


def _call_provider(
    provider: str,
    context: _SearchContext,
    credentials: Mapping[str, str],
) -> tuple[list[dict[str, Any]], str | None]:
    if provider == "serpapi":
        return (
            _search_serpapi(
                context.query,
                context.requested,
                api_key=credentials["api_key"],
                safe_search=context.safe_search,
                timeout=context.api_timeout,
            ),
            None,
        )
    if provider == "google_cse":
        return (
            _search_google_cse(
                context.query,
                context.requested,
                api_key=credentials["api_key"],
                cse_id=credentials["cse_id"],
                safe_search=context.safe_search,
                timeout=context.api_timeout,
            ),
            None,
        )
    if provider == "brave":
        return (
            _search_brave(
                context.query,
                context.requested,
                api_key=credentials["api_key"],
                safe_search=context.safe_search,
                timeout=context.api_timeout,
            ),
            None,
        )
    if provider == "browser":
        return _search_browser(
            context.query,
            context.requested,
            timeout=context.browser_timeout,
            screenshot_path=context.screenshot_target,
        )
    raise ProviderRequestError(f"unknown provider {provider!r}")


def _rank_batch(
    batch: list[dict[str, Any]], context: _SearchContext
) -> list[dict[str, Any]]:
    if not context.ranking_active:
        return batch
    return filter_and_rank_results(
        batch,
        required_terms=context.required,
        optional_terms=context.optional,
        exclude_terms=context.excluded,
        preferred_hosts=context.hosts,
    )


def _record_provider_error(
    ledger: QuotaLedger, provider: str, error: ProviderRequestError
) -> None:
    if error.status == 429:
        ledger.record_cooldown(provider, error.retry_after or 60)
    elif error.status in (401, 403) and _looks_like_quota_error(error.message):
        ledger.mark_exhausted(provider)


def _attempt_provider(
    provider: str, context: _SearchContext
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    configured, credentials, missing_hint = _resolve_credentials(provider)
    if not configured:
        return (
            {
                "provider": provider,
                "status": "skipped",
                "reason": "missing_credentials",
                "missing": missing_hint,
            },
            [],
            None,
        )

    allowed, reason = context.ledger.can_use(provider)
    if not allowed:
        quota = context.ledger.status(provider)
        return (
            {
                "provider": provider,
                "status": "skipped",
                "reason": reason,
                "used": quota.get("used"),
                "limit": quota.get("limit"),
                "reset_at": quota.get("reset_at"),
            },
            [],
            None,
        )

    try:
        batch, screenshot = _call_provider(provider, context, credentials)
    except ProviderRequestError as exc:
        _record_provider_error(context.ledger, provider, exc)
        logger.debug("Image provider %s failed: %s", provider, exc.message)
        return (
            {
                "provider": provider,
                "status": "error",
                "reason": exc.message,
                "http_status": exc.status,
            },
            [],
            None,
        )
    except Exception as exc:  # defensive: the agent loop must keep running
        logger.debug("Image provider %s crashed: %s", provider, exc)
        return (
            {
                "provider": provider,
                "status": "error",
                "reason": _redact_secrets(str(exc)),
            },
            [],
            None,
        )

    context.ledger.record_success(provider)
    batch = _rank_batch(batch, context)
    if batch:
        return (
            {"provider": provider, "status": "ok", "count": len(batch)},
            batch,
            screenshot,
        )
    return ({"provider": provider, "status": "empty"}, [], screenshot)


def _merge_and_rank(
    collected: list[dict[str, Any]],
    batch: list[dict[str, Any]],
    context: _SearchContext,
) -> list[dict[str, Any]]:
    collected.extend(batch)
    return _rank_batch(_dedupe(collected), context)


def _run_provider_chain(
    order: Sequence[str], context: _SearchContext
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    attempts: list[dict[str, Any]] = []
    collected: list[dict[str, Any]] = []
    screenshot: str | None = None

    for provider in order:
        attempt, batch, found_screenshot = _attempt_provider(provider, context)
        if found_screenshot:
            screenshot = found_screenshot
        if attempt:
            attempts.append(attempt)
        if not batch:
            continue
        collected = _merge_and_rank(collected, batch, context)
        if len(collected) >= context.requested:
            break

    return collected[: context.requested], attempts, screenshot


def _success_envelope(
    context: _SearchContext,
    results: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    screenshot: str | None,
) -> dict[str, Any]:
    envelope = {
        "success": True,
        "query": context.query,
        "provider": results[0].get("provider"),
        "count": len(results),
        "results": results,
        "attempts": attempts,
    }
    if screenshot:
        envelope["screenshot"] = screenshot
    return envelope


def _failure_envelope(
    context: _SearchContext, attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in attempts:
        if attempt.get("status") == "error":
            errors.append(f"{attempt['provider']}: {attempt.get('reason') or 'failed'}")
        elif attempt.get("status") == "skipped":
            detail = attempt.get("missing") or attempt.get("reason") or "unavailable"
            errors.append(f"{attempt['provider']}: {detail}")
    return {
        "success": False,
        "query": context.query,
        "provider": None,
        "count": 0,
        "results": [],
        "error": "; ".join(errors)[:500] or "No image provider returned results.",
        "attempts": attempts,
    }



def search_images(
    query: str,
    num_results: int = 3,
    *,
    provider_order: str | Sequence[str] | None = None,
    allow_fallback: bool = True,
    use_quota: bool = True,
    ledger: QuotaLedger | None = None,
    safe_search: str = "active",
    timeout: float | None = None,
    capture_screenshot: bool = False,
    screenshot_path: str | Path | None = None,
    required_terms: str | Sequence[str] | None = None,
    optional_terms: str | Sequence[str] | None = None,
    exclude_terms: str | Sequence[str] | None = None,
    preferred_hosts: str | Sequence[str] | None = None,
) -> dict[str, Any]:
    """Search Google Images through the configured provider chain.

    The keyword-only options mirror the CLI and OpenAI tool schema one-to-one,
    so a request object would only add translation at both boundaries. Revisit
    if a third caller needs to override more than three of them.

    Returns ``{success, query, provider, count, results, attempts}``. On total
    failure ``success`` is ``False`` and every attempt is explained. Never
    raises for provider, network, quota, or browser errors.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return {
            "success": False,
            "query": "",
            "provider": None,
            "count": 0,
            "results": [],
            "error": "query is required",
            "attempts": [],
        }

    try:
        requested = max(1, min(int(num_results), MAX_RESULTS))
    except (TypeError, ValueError):
        requested = 3

    config = get_config()
    order = resolve_provider_order(provider_order)
    if not allow_fallback:
        order = order[:1]

    context = _SearchContext(
        query=clean_query,
        requested=requested,
        safe_search=safe_search,
        api_timeout=float(timeout or getattr(config, "IMAGE_SEARCH_TIMEOUT", 20)),
        browser_timeout=float(getattr(config, "IMAGE_SEARCH_BROWSER_TIMEOUT", 150)),
        screenshot_target=_screenshot_target(screenshot_path) if capture_screenshot else None,
        ledger=ledger
        or QuotaLedger(
            getattr(config, "IMAGE_SEARCH_QUOTA_FILE", None),
            enabled=use_quota and bool(getattr(config, "IMAGE_SEARCH_QUOTA_ENABLED", True)),
        ),
        required=normalise_terms(required_terms),
        optional=normalise_terms(optional_terms),
        excluded=normalise_terms(exclude_terms),
        hosts=normalise_terms(preferred_hosts),
    )

    results, attempts, screenshot = _run_provider_chain(order, context)
    if results:
        return _success_envelope(context, results, attempts, screenshot)
    logger.warning("No image provider returned results for %r", clean_query)
    return _failure_envelope(context, attempts)



# ---------------------------------------------------------------------------
# Agent-facing helpers
# ---------------------------------------------------------------------------


def _escape_markdown_alt(text: str) -> str:
    return re.sub(r"([\\\[\]])", r"\\\1", str(text or ""))


def render_markdown(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    include_source: bool = False,
) -> str:
    """Render results as ``![Title](image_url)`` blocks for a chat UI."""
    if isinstance(payload, Mapping):
        items = payload.get("results") or []
    else:
        items = payload
    blocks: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue
        image_url = str(item.get("image_url") or "").strip()
        if not image_url:
            continue
        alt = _escape_markdown_alt(str(item.get("title") or f"Image {index}"))
        block = f"![{alt}]({image_url})"
        if include_source and item.get("context_url"):
            block += f"\n\nSource: {item['context_url']}"
        blocks.append(block)
    return "\n\n".join(blocks)


IMAGE_SEARCH_RENDERING_HINT = (
    "Render each returned image with standard Markdown: `![Title](image_url)`. "
    "Use `context_url` when the user asks where an image came from."
)

IMAGE_SEARCH_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_google_images",
        "description": (
            "Search Google Images for visual references such as medical figures, "
            "anatomical illustrations, device photographs, or histology examples. "
            "Providers are tried in order (SerpApi, Google Custom Search, Brave, "
            "Playwright fallback) and exhausted free tiers are skipped. Returns a "
            "small list of {title, image_url, thumbnail_url, context_url, provider}. "
            "Use this only when a visual is requested; use the literature tools for papers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific image search query, e.g. 'gingival sulcus histology diagram'.",
                },
                "num_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_RESULTS,
                    "default": 3,
                    "description": "Number of images to return (default 3, maximum 10).",
                },
                "safe_search": {
                    "type": "string",
                    "enum": ["active", "off"],
                    "default": "active",
                    "description": "Keep 'active' unless the user explicitly needs unfiltered results.",
                },
                "required_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Terms that should appear in the title or URL; missing terms lower a result's rank.",
                },
                "exclude_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Terms that disqualify a result, e.g. ['clipart', 'cartoon', 'logo'].",
                },
            },
            "required": ["query"],
        },
    },
}


def get_image_search_tool_schema() -> dict[str, Any]:
    """Return a copy of the OpenAI-style tool schema for agent registration."""
    return copy.deepcopy(IMAGE_SEARCH_TOOL_SCHEMA)


IMAGE_SEARCH_TOOL_NAME = IMAGE_SEARCH_TOOL_SCHEMA["function"]["name"]


def execute_image_search_tool(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Dispatch an OpenAI-style tool-call argument object to ``search_images``.

    Bind ``IMAGE_SEARCH_TOOL_NAME`` to this function when wiring a model's tool
    loop, so the model's JSON arguments need no manual translation.
    """
    if not isinstance(arguments, Mapping):
        return {
            "success": False,
            "query": "",
            "provider": None,
            "count": 0,
            "results": [],
            "error": "tool arguments must be an object",
            "attempts": [],
        }
    return search_images(
        str(arguments.get("query") or ""),
        num_results=arguments.get("num_results", 3),
        safe_search=str(arguments.get("safe_search") or "active"),
        required_terms=arguments.get("required_terms") or None,
        exclude_terms=arguments.get("exclude_terms") or None,
    )


__all__ = [
    "PROVIDER_LABELS",
    "FREE_TIER_LIMITS",
    "MAX_RESULTS",
    "QuotaLedger",
    "ProviderRequestError",
    "resolve_provider_order",
    "get_provider_status",
    "search_images",
    "render_markdown",
    "get_image_search_tool_schema",
    "execute_image_search_tool",
    "IMAGE_SEARCH_TOOL_NAME",
    "IMAGE_SEARCH_TOOL_SCHEMA",
    "IMAGE_SEARCH_RENDERING_HINT",
]
