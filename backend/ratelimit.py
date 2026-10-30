"""In-memory abuse protection for TabSage (Phase 9).

BYOK removes the *AI* bill, not the *infrastructure* bill: an open API that
accepts page text and writes to a store can still be abused to run up compute
and storage cost. This module bounds that with a lightweight, per-client
sliding-window rate limiter plus a per-session ingest cap.

Scope + honesty
---------------
The limiter is **in-memory and per-process**, matching the default ephemeral
in-memory store. It is correct for a single-worker deployment (see the
Dockerfile, which runs one worker by default). A multi-worker / multi-replica
deployment must back both the vector store and this limiter with a shared
service (e.g. pgvector + Redis); the dependency interface here stays the same.

Client identity
---------------
Requests carry an extension-issued anonymous ``X-Client-Token`` so clients are
attributable and throttled individually rather than only by shared IP. When the
token is absent we fall back to the peer IP. The token is **not a secret**, is
never persisted server-side, and is never logged alongside request bodies.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from config import settings


class SlidingWindowRateLimiter:
    """Per-key sliding-window counter.

    Tracks event timestamps per key in a window of ``window_seconds`` and allows
    at most ``max_events`` within any such window. Thread-safe. The ``clock`` is
    injectable so tests can advance time deterministically.
    """

    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_events = max_events
        self.window = float(window_seconds)
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> tuple[bool, float]:
        """Record an attempt for ``key``.

        Returns ``(allowed, retry_after_seconds)``. When blocked, the attempt is
        NOT recorded and ``retry_after_seconds`` is how long until the oldest
        event in the window ages out.
        """
        now = self._clock()
        cutoff = now - self.window
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_events:
                retry_after = events[0] + self.window - now
                return False, max(0.0, retry_after)
            events.append(now)
            return True, 0.0

    def reset(self, key: str | None = None) -> None:
        """Forget one key's history, or all keys when ``key`` is None."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


# ── process-wide limiters (built from settings) ───────────────────────────────
# Per client, across all endpoints — the first line of defense against flooding.
_per_client = SlidingWindowRateLimiter(
    settings.rate_limit_max_requests, settings.rate_limit_window_seconds
)
# Per session, ingest only — bounds how fast one study session can write to the
# store (the main storage/compute cost surface).
_per_session_ingest = SlidingWindowRateLimiter(
    settings.max_ingests_per_window, settings.rate_limit_window_seconds
)


def reset_rate_limiters() -> None:
    """Clear all limiter state. Used by tests between cases."""
    _per_client.reset()
    _per_session_ingest.reset()


def _client_key(request: Request, token: str | None) -> str:
    """Throttle key: the anonymous client token if present, else the peer IP."""
    tok = (token or "").strip()
    if tok:
        return f"token:{tok}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def _too_many(retry_after: float, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, int(retry_after) + 1))},
    )


async def enforce_client_rate_limit(
    request: Request,
    x_client_token: Annotated[str | None, Header()] = None,
) -> None:
    """FastAPI dependency: throttle every request per client.

    Raises 429 (with a ``Retry-After`` header) when the client exceeds the
    per-window request budget. Applied to /ingest, /chat, and /sessions/reset;
    /health is intentionally exempt so uptime checks are never throttled.
    """
    key = _client_key(request, x_client_token)
    allowed, retry_after = _per_client.hit(key)
    if not allowed:
        raise _too_many(
            retry_after,
            "Too many requests. Slow down and try again in a moment.",
        )


def enforce_ingest_quota(session_id: str) -> None:
    """Per-session ingest cap. Called inside the /ingest handler.

    Bounds how many pages a single session can push into the store within the
    window, independent of the global per-client limit above.
    """
    allowed, retry_after = _per_session_ingest.hit(session_id)
    if not allowed:
        raise _too_many(
            retry_after,
            "This session is adding tabs too quickly. Wait a moment before "
            "adding another.",
        )
