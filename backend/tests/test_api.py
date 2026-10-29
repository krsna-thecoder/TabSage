"""API endpoint tests (Phase 6) via FastAPI TestClient — offline.

The `client` fixture (conftest) patches `main.get_provider` with `fake_factory`,
so no real key/network is used. Unique session ids keep tests isolated in the
app's shared process-wide store.
"""
from __future__ import annotations

import uuid

import pytest

KEY = {"X-Provider-Key": "test-key"}

BIN_TEXT = (
    "Binary search is an efficient algorithm for finding an item in a sorted "
    "list. It repeatedly halves the interval, giving O(log n) time."
)
HTTP_TEXT = "HTTP is a stateless request response protocol with status codes."


def _sid() -> str:
    return f"api-{uuid.uuid4().hex[:12]}"


def _ingest_body(session, tab_id, text, title="T", url="https://ex/t"):
    return {
        "tab_id": tab_id, "title": title, "url": url,
        "text": text, "session_id": session, "provider": "gemini",
    }


# ── health ───────────────────────────────────────────────────────────────────
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_redirects_to_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/docs"


# ── auth guard ─────────────────────────────────────────────────────────────
def test_ingest_without_key_is_401(client):
    r = client.post("/ingest", json=_ingest_body(_sid(), "t1", BIN_TEXT))
    assert r.status_code == 401


def test_chat_without_key_is_401(client):
    r = client.post("/chat", json={"question": "hi", "session_id": _sid(),
                                   "provider": "gemini"})
    assert r.status_code == 401


# ── schema validation ────────────────────────────────────────────────────────
def test_ingest_empty_text_is_422(client):
    r = client.post("/ingest", headers=KEY, json=_ingest_body(_sid(), "t1", ""))
    assert r.status_code == 422


def test_ingest_whitespace_text_is_422(client):
    r = client.post("/ingest", headers=KEY, json=_ingest_body(_sid(), "t1", "     "))
    assert r.status_code == 422


def test_chat_overlong_question_is_422(client):
    r = client.post("/chat", headers=KEY, json={
        "question": "a" * 5000, "session_id": _sid(), "provider": "gemini"})
    assert r.status_code == 422


# ── happy path: ingest → chat → reset ────────────────────────────────────────
def test_ingest_then_chat_grounded(client):
    sid = _sid()
    r1 = client.post("/ingest", headers=KEY,
                     json=_ingest_body(sid, "tab-bin", BIN_TEXT, "Binary", "https://ex/bin"))
    assert r1.status_code == 200
    assert r1.json()["chunks_indexed"] >= 1

    rc = client.post("/chat", headers=KEY, json={
        "question": "How fast is binary search?", "session_id": sid, "provider": "gemini"})
    assert rc.status_code == 200
    body = rc.json()
    assert body["grounded"] is True
    assert len(body["citations"]) >= 1
    assert body["answer"]


def test_chat_bad_filter_refuses(client):
    sid = _sid()
    client.post("/ingest", headers=KEY, json=_ingest_body(sid, "tab-bin", BIN_TEXT))
    rf = client.post("/chat", headers=KEY, json={
        "question": "anything", "session_id": sid, "provider": "gemini",
        "source_tab_ids": ["does-not-exist"]})
    assert rf.status_code == 200
    assert rf.json()["grounded"] is False
    assert rf.json()["citations"] == []


def test_reset_then_chat_refuses(client):
    sid = _sid()
    client.post("/ingest", headers=KEY, json=_ingest_body(sid, "tab-bin", BIN_TEXT))
    rr = client.post("/sessions/reset", json={"session_id": sid})
    assert rr.status_code == 200
    assert rr.json()["chunks_removed"] >= 1

    ra = client.post("/chat", headers=KEY, json={
        "question": "How fast is binary search?", "session_id": sid, "provider": "gemini"})
    assert ra.json()["grounded"] is False


# ── provider error → HTTP mapping ─────────────────────────────────────────────
def test_chat_bad_key_is_401(client):
    r = client.post("/chat", headers={"X-Provider-Key": "BADKEY"}, json={
        "question": "hi", "session_id": _sid(), "provider": "gemini"})
    assert r.status_code == 401


def test_chat_rate_limit_is_429(client):
    sid = _sid()
    client.post("/ingest", headers=KEY, json=_ingest_body(sid, "tab-bin", BIN_TEXT))
    r = client.post("/chat", headers=KEY, json={
        "question": "RATELIMIT please", "session_id": sid, "provider": "gemini"})
    assert r.status_code == 429


def test_ingest_model_switch_is_409(client):
    sid = _sid()
    client.post("/ingest", headers=KEY, json=_ingest_body(sid, "tab-bin", BIN_TEXT))
    # Re-ingest the same session with a provider reporting a different model.
    r = client.post("/ingest", headers={"X-Provider-Key": "MODELV2"},
                    json=_ingest_body(sid, "tab-bin", BIN_TEXT))
    assert r.status_code == 409


def test_ingest_over_source_cap_is_413(client, monkeypatch):
    import main
    monkeypatch.setattr(main.settings, "max_sources_per_session", 1)
    sid = _sid()
    r1 = client.post("/ingest", headers=KEY, json=_ingest_body(sid, "a", BIN_TEXT))
    assert r1.status_code == 200
    r2 = client.post("/ingest", headers=KEY, json=_ingest_body(sid, "b", HTTP_TEXT))
    assert r2.status_code == 413


# ── CORS ──────────────────────────────────────────────────────────────────────
def test_cors_allows_configured_origin(client):
    pre = client.options("/chat", headers={
        "Origin": "http://localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-provider-key"})
    assert pre.status_code == 200
    assert pre.headers.get("access-control-allow-origin") == "http://localhost"


def test_cors_blocks_unknown_origin(client):
    bad = client.options("/chat", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "POST"})
    assert bad.headers.get("access-control-allow-origin") in (None, "")
