"""Local free-tier quota ledger for the image-search provider chain.

The ledger is deliberately small and dependency-free. It records one counter
per provider per billing period, plus a short cooldown after a 429. It cannot
see usage from other machines or tools sharing a key, so the provider dashboard
remains authoritative.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

FREE_TIER_LIMITS: dict[str, dict[str, Any]] = {
    "serpapi": {
        "limit": 100,
        "period": "month",
        "note": "SerpApi free plan: 100 searches/month.",
    },
    "google_cse": {
        "limit": 100,
        "period": "day",
        "note": "Google Custom Search JSON API: 100 queries/day free (10,000/day cap).",
    },
    "brave": {
        "limit": 2000,
        "period": "month",
        "note": "Brave Search free plan: 2,000 queries/month at 1 request/second.",
    },
    "browser": {
        "limit": None,
        "period": None,
        "note": "No API quota. Slower; may hit CAPTCHA or a consent wall.",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _period_key(period: str | None, now: datetime) -> str:
    if period == "day":
        return now.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m")


def _period_reset(period: str | None, now: datetime) -> datetime:
    if period == "day":
        tomorrow = (now + timedelta(days=1)).date()
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)
    year, month = now.year, now.month
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc)


class QuotaLedger:
    """Local, atomic, best-effort record of provider usage.

    Pass ``enabled=False`` for a memory-only ledger (useful in tests or when the
    workspace is read-only).
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        enabled: bool = True,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path else None
        self.enabled = enabled
        self._now = now or _utcnow
        self._lock = threading.Lock()
        self._memory: dict[str, Any] = {"version": 1, "providers": {}}

    def _read(self) -> dict[str, Any]:
        if not self.enabled or self.path is None:
            return copy.deepcopy(self._memory)
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(state, dict) and isinstance(state.get("providers"), dict):
                return state
        except (OSError, ValueError):
            pass
        return {"version": 1, "providers": {}}

    def _write(self, state: dict[str, Any]) -> None:
        if not self.enabled or self.path is None:
            self._memory = state
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("Could not persist image-search quota ledger: %s", exc)
            self._memory = state

    def _entry(self, state: dict[str, Any], provider: str) -> dict[str, Any]:
        providers = state.setdefault("providers", {})
        entry = providers.get(provider)
        if not isinstance(entry, dict):
            entry = {}
            providers[provider] = entry
        return entry

    def status(self, provider: str) -> dict[str, Any]:
        info = FREE_TIER_LIMITS.get(provider, {})
        limit = info.get("limit")
        period = info.get("period")
        now = self._now()
        current = _period_key(period, now)

        with self._lock:
            state = self._read()
            entry = self._entry(state, provider)
            used = (
                int(entry.get("used", 0) or 0)
                if entry.get("period") == current
                else 0
            )
            cooldown = float(entry.get("cooldown_until", 0) or 0)

        remaining = None if limit is None else max(0, limit - used)
        return {
            "provider": provider,
            "limit": limit,
            "used": used,
            "remaining": remaining,
            "period": period,
            "reset_at": _period_reset(period, now).isoformat() if period else None,
            "cooldown_until": cooldown or None,
        }

    def can_use(self, provider: str) -> tuple[bool, str | None]:
        status = self.status(provider)
        if status["limit"] is None:
            return True, None
        cooldown = status.get("cooldown_until")
        if cooldown and float(cooldown) > self._now().timestamp():
            return False, "rate_limited"
        if int(status["remaining"] or 0) <= 0:
            return False, "quota_exhausted"
        return True, None

    def record_success(self, provider: str) -> None:
        info = FREE_TIER_LIMITS.get(provider, {})
        if not self.enabled or info.get("limit") is None:
            return
        current = _period_key(info.get("period"), self._now())
        with self._lock:
            state = self._read()
            entry = self._entry(state, provider)
            if entry.get("period") != current:
                entry["period"] = current
                entry["used"] = 0
            entry["used"] = int(entry.get("used", 0) or 0) + 1
            self._write(state)

    def mark_exhausted(self, provider: str) -> None:
        info = FREE_TIER_LIMITS.get(provider, {})
        limit = info.get("limit")
        if not self.enabled or limit is None:
            return
        current = _period_key(info.get("period"), self._now())
        with self._lock:
            state = self._read()
            entry = self._entry(state, provider)
            entry["period"] = current
            entry["used"] = int(limit)
            self._write(state)

    def record_cooldown(self, provider: str, seconds: float) -> None:
        if not self.enabled:
            return
        until = self._now().timestamp() + max(1.0, float(seconds))
        with self._lock:
            state = self._read()
            entry = self._entry(state, provider)
            entry["cooldown_until"] = max(
                float(entry.get("cooldown_until", 0) or 0), until
            )
            self._write(state)


__all__ = ["FREE_TIER_LIMITS", "QuotaLedger"]
