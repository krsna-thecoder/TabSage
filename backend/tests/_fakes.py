"""Shared offline fakes for the Phase 11 test suite.

No real provider key or network is ever used. `FakeProvider` gives
deterministic, hash-based embeddings so similarity is reproducible, and a
scriptable `generate` so the chat/endpoint paths can be driven precisely.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from providers.base import BaseProvider, ProviderAuthError, ProviderRateLimit
from schemas import Provider

EMBED_DIM = 128


def fake_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic bag-of-words unit vector: shared words → higher cosine."""
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider(BaseProvider):
    """Offline provider with deterministic embeddings and a scripted answer.

    * `embedding_model` is overridable so the embedding-consistency guard can be
      exercised (two FakeProviders with different model ids).
    * `generate` returns `canned_answer`, but raises `ProviderRateLimit` if the
      prompt contains the marker "RATELIMIT" (used by the API error-path tests).
    """

    provider_name = "fake"
    embedding_model = "fake-embed-v1"
    generation_model = "fake-gen"

    def __init__(
        self,
        embedding_model: str = "fake-embed-v1",
        canned_answer: str = "Binary search runs in O(log n) time [1].",
    ) -> None:
        # Skip BaseProvider's key requirement — this never calls a network.
        self.embedding_model = embedding_model
        self._api_key = "n/a"
        self._canned = canned_answer
        self.generate_calls = 0
        self.embed_calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls += 1
        return [fake_embed(t) for t in texts]

    def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        if "RATELIMIT" in prompt:
            raise ProviderRateLimit("Fake rate limit hit.")
        return self._canned


def fake_factory(provider: Provider, api_key: str) -> FakeProvider:
    """Stand-in for `providers.get_provider`, keyed off magic test keys.

        "BADKEY"  → raises ProviderAuthError (→ 401)
        "MODELV2" → reports a different embedding model (→ 409 mismatch)
        otherwise → a normal FakeProvider
    """
    if api_key == "BADKEY":
        raise ProviderAuthError("Invalid or unauthorized fake API key.")
    if api_key == "MODELV2":
        return FakeProvider(embedding_model="fake-embed-v2")
    return FakeProvider()
