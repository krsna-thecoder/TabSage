"""Rate-limiting / abuse-protection tests (Phase 9).

Two layers:
  * unit tests for `SlidingWindowRateLimiter` with an injected clock, and
  * endpoint tests that drive the real dependencies through the TestClient
    (limits temporarily lowered so a few requests are enough to trip them).
"""
from __future__ import annotations

import uuid

import pytest

import ratelimit
from ratelimit import SlidingWindowRateLimiter

KEY = {"X-Provider-Key": "test-key"}
BIN_TEXT = (
    "Binary search is an efficient algorithm for finding an item in a sorted "
    "list. It repeatedly halves the interval, giving O(log n) time."
)
HTTP_TEXT = "HTTP is a stateless request response protocol with status codes."


def _sid() -> str:
    return f"rl-{uuid.uuid4().hex[:12]}"


def _ingest_body(session, tab_id, text, title="T", url="https://ex/t"):
    return {
        "tab_id": tab_id, "title": title, "url": url,
        "text": text, "session_id": session, "provider": "gemini",
    }


# ── unit: the sliding window ────────────────────────────────────────────────
def test_allows_up_to_limit_then_blocks():
    now = [0.0]
    rl = SlidingWindowRateLimiter(3, 10, clock=lambda: now[0])
    assert rl.hit("k")[0] is True
    assert rl.hit("k")[0] is True
    assert rl.hit("k")[0] is True
    allowed, retry_after = rl.hit("k")
    assert allowed is False
    assert retry_after > 0


def test_window_slides_and_frees_capacity():
    now = [0.0]
    rl = SlidingWindowRateLimiter(2, 10, clock=lambda: now[0])
    assert rl.hit("k")[0] is True
    assert rl.hit("k")[0] is True
    assert rl.hit("k")[0] is False
    now[0] = 10.1  # oldest events age out of the window
    assert rl.hit("k")[0] is True


def test_keys_are_isolated():
    rl = SlidingWindowRateLimiter(1, 10)
    assert rl.hit("a")[0] is True
    assert rl.hit("a")[0] is False
    assert rl.hit("b")[0] is True  # a different client is unaffected


def test_reset_one_key_and_all():
    rl = SlidingWindowRateLimiter(1, 10)
    rl.hit("a")
    rl.hit("b")
    rl.reset("a")
    assert rl.hit("a")[0] is True   # a cleared
    assert rl.hit("b")[0] is False  # b untouched
    rl.reset()
    assert rl.hit("b")[0] is True   # all cleared


def test_blocked_attempt_is_not_counted():
    now = [0.0]
    rl = SlidingWindowRateLimiter(1, 10, clock=lambda: now[0])
    assert rl.hit("k")[0] is True
    assert rl.hit("k")[0] is False
    now[0] = 10.1
    # Only the first (allowed) hit was recorded, so capacity is free again.
    assert rl.hit("k")[0] is True


# ── endpoint: per-client throttle ────────────────────────────────────────────
def test_per_client_rate_limit_returns_429(client):
    original = ratelimit._per_client.max_events
    ratelimit._per_client.max_events = 2
    try:
        h = {"X-Client-Token": "tok-A"}
        assert client.post("/sessions/reset", json={"session_id": "s"}, headers=h).status_code == 200
        assert client.post("/sessions/reset", json={"session_id": "s"}, headers=h).status_code == 200
        r = client.post("/sessions/reset", json={"session_id": "s"}, headers=h)
        assert r.status_code == 429
        assert r.headers.get("Retry-After")
    finally:
        ratelimit._per_client.max_events = original


def test_per_client_limit_is_per_token(client):
    original = ratelimit._per_client.max_events
    ratelimit._per_client.max_events = 1
    try:
        a = {"X-Client-Token": "tok-A"}
        b = {"X-Client-Token": "tok-B"}
        assert client.post("/sessions/reset", json={"session_id": "s"}, headers=a).status_code == 200
        assert client.post("/sessions/reset", json={"session_id": "s"}, headers=a).status_code == 429
        # A different client token has its own bucket.
        assert client.post("/sessions/reset", json={"session_id": "s"}, headers=b).status_code == 200
    finally:
        ratelimit._per_client.max_events = original


# ── endpoint: per-session ingest quota ───────────────────────────────────────
def test_per_session_ingest_quota_returns_429(client):
    original = ratelimit._per_session_ingest.max_events
    ratelimit._per_session_ingest.max_events = 1
    try:
        sid = _sid()
        r1 = client.post("/ingest", headers=KEY, json=_ingest_body(sid, "a", BIN_TEXT))
        assert r1.status_code == 200
        r2 = client.post("/ingest", headers=KEY, json=_ingest_body(sid, "b", HTTP_TEXT))
        assert r2.status_code == 429
        assert r2.headers.get("Retry-After")
    finally:
        ratelimit._per_session_ingest.max_events = original


def test_health_is_not_rate_limited(client):
    original = ratelimit._per_client.max_events
    ratelimit._per_client.max_events = 1
    try:
        for _ in range(5):
            assert client.get("/health").status_code == 200
    finally:
        ratelimit._per_client.max_events = original
