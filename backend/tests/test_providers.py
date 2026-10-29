"""Provider-layer tests (Phase 11) — fully mocked, never a real key/network.

Covers:
* BaseProvider key handling, repr safety, embedding_model_id.
* retry_with_backoff semantics (injected sleep → instant).
* Factory selection + unknown-provider guard.
* Vendor error → normalized ProviderError mapping (Gemini + OpenAI).
* Embedding batching splits correctly.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx2
import openai
import pytest
from google.genai import errors as genai_errors

from providers import (
    GeminiProvider,
    OpenAIProvider,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
    get_provider,
    retry_with_backoff,
)
from providers.base import RETRYABLE, BaseProvider
from providers.gemini import _map_error as gemini_map
from providers.openai import _map_error as openai_map
from schemas import Provider


# ── BaseProvider basics ─────────────────────────────────────────────────────
class _Dummy(BaseProvider):
    provider_name = "dummy"
    embedding_model = "dummy-embed"
    generation_model = "dummy-gen"

    def embed(self, texts):  # pragma: no cover - not exercised here
        return [[0.0] for _ in texts]

    def generate(self, prompt):  # pragma: no cover
        return "x"


def test_missing_key_raises_auth_error():
    with pytest.raises(ProviderAuthError):
        _Dummy("")
    with pytest.raises(ProviderAuthError):
        _Dummy("   ")


def test_repr_never_leaks_key():
    p = _Dummy("super-secret-key-123")
    assert "super-secret-key-123" not in repr(p)


def test_embedding_model_id_format():
    assert _Dummy("k").embedding_model_id == "dummy:dummy-embed"


# ── retry_with_backoff ───────────────────────────────────────────────────────
def test_retry_returns_on_first_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert retry_with_backoff(fn, sleep=lambda _: None) == "ok"
    assert calls["n"] == 1


def test_retry_recovers_after_transient_errors():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderRateLimit("try again")
        return "ok"

    assert retry_with_backoff(fn, max_attempts=5, sleep=lambda _: None) == "ok"
    assert calls["n"] == 3


def test_retry_exhausts_and_reraises_last_error():
    def fn():
        raise ProviderUnavailable("still down")

    with pytest.raises(ProviderUnavailable):
        retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)


def test_retry_does_not_retry_nonretryable():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ProviderAuthError("bad key")

    with pytest.raises(ProviderAuthError):
        retry_with_backoff(fn, max_attempts=5, sleep=lambda _: None)
    assert calls["n"] == 1  # not retried


def test_retryable_set_membership():
    assert ProviderRateLimit in RETRYABLE
    assert ProviderTimeout in RETRYABLE
    assert ProviderUnavailable in RETRYABLE
    assert ProviderAuthError not in RETRYABLE
    assert ProviderBadRequest not in RETRYABLE


# ── factory ─────────────────────────────────────────────────────────────────
def test_factory_selects_implementation():
    assert isinstance(get_provider(Provider.gemini, "k"), GeminiProvider)
    assert isinstance(get_provider(Provider.openai, "k"), OpenAIProvider)


def test_factory_unknown_provider_raises():
    with pytest.raises(ProviderError):
        get_provider("nope", "k")  # type: ignore[arg-type]


# ── Gemini error mapping ─────────────────────────────────────────────────────
def _api_err(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "x", "status": "S"}})


@pytest.mark.parametrize(
    "code, expected",
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimit),
        (408, ProviderTimeout),
        (504, ProviderTimeout),
        (400, ProviderBadRequest),
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
    ],
)
def test_gemini_map_error_codes(code, expected):
    assert isinstance(gemini_map(_api_err(code)), expected)


def test_gemini_map_error_non_api_is_unavailable():
    assert isinstance(gemini_map(ConnectionError("no route")), ProviderUnavailable)


# ── OpenAI error mapping ─────────────────────────────────────────────────────
def _resp(code: int) -> httpx2.Response:
    return httpx2.Response(code, request=httpx2.Request("POST", "https://api.openai.com/v1/x"))


def test_openai_map_auth():
    exc = openai.AuthenticationError("bad", response=_resp(401), body=None)
    assert isinstance(openai_map(exc), ProviderAuthError)


def test_openai_map_rate_limit():
    exc = openai.RateLimitError("rl", response=_resp(429), body=None)
    assert isinstance(openai_map(exc), ProviderRateLimit)


def test_openai_map_timeout():
    exc = openai.APITimeoutError(request=httpx2.Request("POST", "https://x"))
    assert isinstance(openai_map(exc), ProviderTimeout)


def test_openai_map_bad_request():
    exc = openai.BadRequestError("bad", response=_resp(400), body=None)
    assert isinstance(openai_map(exc), ProviderBadRequest)


def test_openai_map_connection_is_unavailable():
    exc = openai.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    assert isinstance(openai_map(exc), ProviderUnavailable)


def test_openai_map_unknown_is_generic_provider_error():
    assert isinstance(openai_map(ValueError("weird")), ProviderError)


# ── embedding batching ───────────────────────────────────────────────────────
def _fake_embed_models():
    """A fake `client.models` recording each embed_content batch."""
    recorder: list[list[str]] = []

    class Models:
        def embed_content(self, model, contents):
            recorder.append(list(contents))
            return SimpleNamespace(
                embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3]) for _ in contents]
            )

    return Models(), recorder


def test_gemini_embed_batches_by_batch_size():
    p = GeminiProvider("fake-key")
    models, recorder = _fake_embed_models()
    p._client = SimpleNamespace(models=models)
    p.embed_batch_size = 2

    out = p.embed(["a", "b", "c", "d", "e"])

    assert len(out) == 5
    assert [len(b) for b in recorder] == [2, 2, 1]  # 5 texts → 3 batched calls


def test_gemini_embed_empty_returns_empty():
    p = GeminiProvider("fake-key")
    assert p.embed([]) == []


def test_gemini_embed_maps_bad_request(monkeypatch):
    # 400 is non-retryable, so this raises immediately (no backoff sleep).
    p = GeminiProvider("fake-key")

    class Models:
        def embed_content(self, model, contents):
            raise _api_err(400)

    p._client = SimpleNamespace(models=Models())
    with pytest.raises(ProviderBadRequest):
        p.embed(["x"])
