"""Manual Phase 6 check — API endpoints, offline (no key, no network).

Usage (from backend/, venv active):
    python scripts/try_api.py

Drives the FastAPI app with `TestClient`, monkeypatching the provider factory
with a deterministic fake so /ingest, /chat and /sessions/reset can be
exercised end-to-end without a real key. It checks the happy paths, the honest
refusal, the error→HTTP-status mapping, payload caps, and CORS preflight.

Fake-key conventions used to trigger specific paths:
    "BADKEY"   -> provider raises ProviderAuthError (expect 401)
    "MODELV2"  -> provider reports a different embedding model (expect 409)
    otherwise  -> normal fake provider
A question containing "RATELIMIT" makes generate() raise ProviderRateLimit (429).
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from collections.abc import Sequence

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from providers.base import (  # noqa: E402
    BaseProvider,
    ProviderAuthError,
    ProviderRateLimit,
)
from schemas import Provider  # noqa: E402


def _hash_embed(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider(BaseProvider):
    provider_name = "fake"
    embedding_model = "fake-embed-v1"
    generation_model = "fake-gen"

    def __init__(self, embedding_model: str = "fake-embed-v1") -> None:
        self._api_key = "n/a"
        self.embedding_model = embedding_model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]

    def generate(self, prompt: str) -> str:
        if "RATELIMIT" in prompt:
            raise ProviderRateLimit("Fake rate limit hit.")
        return "Binary search runs in O(log n) time [1]."


def _fake_factory(provider: Provider, api_key: str) -> FakeProvider:
    if api_key == "BADKEY":
        raise ProviderAuthError("Invalid or unauthorized fake API key.")
    if api_key == "MODELV2":
        return FakeProvider(embedding_model="fake-embed-v2")
    return FakeProvider()


# Patch the factory the endpoints call.
main.get_provider = _fake_factory

client = TestClient(main.app)
KEY = {"X-Provider-Key": "test-key"}

_passed = 0
_failed = 0


def check(label: str, got, expected) -> None:
    global _passed, _failed
    ok = got == expected
    _passed += ok
    _failed += not ok
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] {label}: got {got!r} expected {expected!r}")


def check_true(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    _passed += bool(cond)
    _failed += not cond
    print(f"[{'OK ' if cond else 'FAIL'}] {label} {detail}".rstrip())


def ingest_body(session, tab_id, text, title="T", url="https://ex/t"):
    return {
        "tab_id": tab_id, "title": title, "url": url,
        "text": text, "session_id": session, "provider": "gemini",
    }


BIN_TEXT = (
    "Binary search is an efficient algorithm for finding an item in a sorted "
    "list. It repeatedly halves the interval, giving O(log n) time."
)


def main_check() -> int:
    print("=" * 70, "\nPhase 6 endpoint checks (offline)\n", "=" * 70, sep="")

    # health
    r = client.get("/health")
    check("GET /health status", r.status_code, 200)
    check("GET /health body", r.json(), {"status": "ok"})

    # auth guard
    check("POST /ingest no key -> 401",
          client.post("/ingest", json=ingest_body("s1", "tab1", BIN_TEXT)).status_code,
          401)

    # schema validation: empty text
    check("POST /ingest empty text -> 422",
          client.post("/ingest", headers=KEY,
                      json=ingest_body("s1", "tab1", "")).status_code, 422)

    # whitespace-only text -> EmptyContentError -> 422
    check("POST /ingest whitespace text -> 422",
          client.post("/ingest", headers=KEY,
                      json=ingest_body("s1", "tab1", "     ")).status_code, 422)

    # happy ingest x2
    r1 = client.post("/ingest", headers=KEY, json=ingest_body("s1", "tab-bin", BIN_TEXT,
                                                              "Binary Search", "https://ex/bin"))
    check("POST /ingest tab-bin -> 200", r1.status_code, 200)
    check_true("  chunks_indexed >= 1", r1.json().get("chunks_indexed", 0) >= 1,
               f"(={r1.json().get('chunks_indexed')})")
    r2 = client.post("/ingest", headers=KEY, json=ingest_body("s1", "tab-http",
                     "HTTP is a stateless request response protocol with status codes.",
                     "HTTP", "https://ex/http"))
    check("POST /ingest tab-http -> 200", r2.status_code, 200)

    # chat in-context
    rc = client.post("/chat", headers=KEY, json={
        "question": "How fast is binary search?", "session_id": "s1", "provider": "gemini"})
    check("POST /chat in-context -> 200", rc.status_code, 200)
    body = rc.json()
    check_true("  grounded True", body.get("grounded") is True)
    check_true("  has citations", len(body.get("citations", [])) >= 1,
               f"(n={len(body.get('citations', []))})")
    check_true("  answer non-empty", bool(body.get("answer")))

    # chat filtered to a non-existent tab -> honest refusal
    rf = client.post("/chat", headers=KEY, json={
        "question": "anything", "session_id": "s1", "provider": "gemini",
        "source_tab_ids": ["does-not-exist"]})
    check("POST /chat bad filter -> 200", rf.status_code, 200)
    check_true("  grounded False (refusal)", rf.json().get("grounded") is False)
    check_true("  no citations", rf.json().get("citations") == [])

    # chat no key
    check("POST /chat no key -> 401",
          client.post("/chat", json={"question": "hi", "session_id": "s1"}).status_code, 401)

    # question too long
    check("POST /chat overlong question -> 422",
          client.post("/chat", headers=KEY, json={
              "question": "a" * 5000, "session_id": "s1", "provider": "gemini"}).status_code,
          422)

    # provider auth error mapping
    check("POST /chat BADKEY -> 401",
          client.post("/chat", headers={"X-Provider-Key": "BADKEY"}, json={
              "question": "hi", "session_id": "s1", "provider": "gemini"}).status_code, 401)

    # rate limit mapping
    check("POST /chat RATELIMIT -> 429",
          client.post("/chat", headers=KEY, json={
              "question": "RATELIMIT please", "session_id": "s1", "provider": "gemini"}).status_code,
          429)

    # embedding-model mismatch -> 409 (re-ingest same session with a different model)
    check("POST /ingest model switch -> 409",
          client.post("/ingest", headers={"X-Provider-Key": "MODELV2"},
                      json=ingest_body("s1", "tab-bin", BIN_TEXT)).status_code, 409)

    # max sources cap -> 413 (temporarily set the cap to 1)
    old_cap = main.settings.max_sources_per_session
    main.settings.max_sources_per_session = 1
    try:
        client.post("/ingest", headers=KEY, json=ingest_body("scap", "a", BIN_TEXT))
        check("POST /ingest over source cap -> 413",
              client.post("/ingest", headers=KEY,
                          json=ingest_body("scap", "b", BIN_TEXT)).status_code, 413)
    finally:
        main.settings.max_sources_per_session = old_cap

    # reset
    rr = client.post("/sessions/reset", json={"session_id": "s1"})
    check("POST /sessions/reset -> 200", rr.status_code, 200)
    check_true("  chunks_removed > 0", rr.json().get("chunks_removed", 0) > 0,
               f"(={rr.json().get('chunks_removed')})")
    # after reset, chat -> refusal
    ra = client.post("/chat", headers=KEY, json={
        "question": "How fast is binary search?", "session_id": "s1", "provider": "gemini"})
    check_true("  chat after reset -> refusal", ra.json().get("grounded") is False)

    # CORS preflight — allowed origin is echoed (never "*")
    pre = client.options("/chat", headers={
        "Origin": "http://localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-provider-key"})
    check("CORS preflight allowed -> 200", pre.status_code, 200)
    check("  echoes origin (not *)",
          pre.headers.get("access-control-allow-origin"), "http://localhost")
    # disallowed origin gets no allow-origin header
    bad = client.options("/chat", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "POST"})
    check_true("  disallowed origin blocked",
               bad.headers.get("access-control-allow-origin") in (None, ""),
               f"(header={bad.headers.get('access-control-allow-origin')!r})")

    print("\n" + "=" * 70)
    print(f"RESULT: {_passed} passed, {_failed} failed")
    print("=" * 70)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main_check())
