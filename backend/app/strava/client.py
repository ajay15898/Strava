"""Rate-limited Strava HTTP client.

Strava enforces a short-window limit and a daily limit, and the published
numbers have changed over time. Nothing here hardcodes them: the limiter reads
`X-RateLimit-Limit` / `X-RateLimit-Usage` (and the read-only variants) off every
response and adapts. Before a request that would cross the short-window budget
it sleeps until the window rolls; on a 429 it honours `Retry-After`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://www.strava.com/api/v3"

# Strava's short window is 15 minutes, aligned to the clock.
SHORT_WINDOW_S = 15 * 60

# Leave a little of the short-window budget unspent so an interactive request
# is not starved by a running backfill.
SHORT_WINDOW_RESERVE = 5


def _parse_pair(value: str | None) -> tuple[int, int] | None:
    """Parse a Strava `short,daily` header into ints."""
    if not value:
        return None
    parts = value.split(",")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None


@dataclass
class RateLimitState:
    short_limit: int | None = None
    short_usage: int | None = None
    daily_limit: int | None = None
    daily_usage: int | None = None
    updated_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def observe(self, headers: httpx.Headers) -> None:
        # Prefer the read-specific counters when present; the general ones also
        # count writes, which a backfill never makes.
        limit = _parse_pair(headers.get("x-readratelimit-limit")) or _parse_pair(
            headers.get("x-ratelimit-limit")
        )
        usage = _parse_pair(headers.get("x-readratelimit-usage")) or _parse_pair(
            headers.get("x-ratelimit-usage")
        )
        with self._lock:
            if limit:
                self.short_limit, self.daily_limit = limit
            if usage:
                self.short_usage, self.daily_usage = usage
            self.updated_at = time.time()

    @property
    def daily_exhausted(self) -> bool:
        if self.daily_limit is None or self.daily_usage is None:
            return False
        return self.daily_usage >= self.daily_limit

    def seconds_until_window_reset(self) -> float:
        now = time.time()
        return SHORT_WINDOW_S - (now % SHORT_WINDOW_S)

    def should_pause(self) -> float:
        """Seconds to sleep before the next request, 0 if clear to proceed."""
        with self._lock:
            if self.short_limit is None or self.short_usage is None:
                return 0.0
            if self.short_usage >= max(self.short_limit - SHORT_WINDOW_RESERVE, 1):
                return self.seconds_until_window_reset() + 1.0
        return 0.0


class StravaRateLimitError(RuntimeError):
    """Daily quota exhausted — the caller should stop, not retry."""


class StravaClient:
    def __init__(
        self,
        access_token: str,
        *,
        limiter: RateLimitState | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 4,
    ) -> None:
        self.access_token = access_token
        self.limiter = limiter or RateLimitState()
        self.max_retries = max_retries
        self._client = client or httpx.Client(base_url=API_BASE, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StravaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.access_token}"}

        for attempt in range(self.max_retries):
            if self.limiter.daily_exhausted:
                raise StravaRateLimitError("Strava daily read quota exhausted")

            pause = self.limiter.should_pause()
            if pause:
                log.warning("rate limit near cap, sleeping %.0fs for window reset", pause)
                time.sleep(pause)

            resp = self._client.get(path, params=params, headers=headers)
            self.limiter.observe(resp.headers)

            if resp.status_code == 429:
                if self.limiter.daily_exhausted:
                    raise StravaRateLimitError("Strava daily read quota exhausted")
                retry_after = resp.headers.get("retry-after")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else self.limiter.seconds_until_window_reset() + 1.0
                )
                log.warning("429 from Strava, backing off %.0fs", delay)
                time.sleep(delay)
                continue

            if resp.status_code >= 500:
                delay = 2**attempt
                log.warning("Strava %s, retrying in %ss", resp.status_code, delay)
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json()

        raise RuntimeError(f"Strava request failed after {self.max_retries} attempts: {path}")

    # --- endpoints -------------------------------------------------------

    def athlete(self) -> dict:
        return self.get("/athlete")

    def zones(self) -> dict:
        return self.get("/athlete/zones")

    def activities(
        self, *, after: int | None = None, before: int | None = None, page: int = 1, per_page: int = 100
    ) -> list[dict]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        return self.get("/athlete/activities", params)

    def activity(self, activity_id: int) -> dict:
        return self.get(f"/activities/{activity_id}", {"include_all_efforts": "true"})

    def streams(self, activity_id: int, keys: list[str] | None = None) -> dict:
        keys = keys or [
            "time",
            "distance",
            "heartrate",
            "velocity_smooth",
            "altitude",
            "cadence",
            "watts",
        ]
        return self.get(
            f"/activities/{activity_id}/streams",
            {"keys": ",".join(keys), "key_by_type": "true"},
        )
