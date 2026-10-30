"""Gemini provider (default) — uses the `google-genai` SDK.

Why `google-genai` (not the deprecated `google-generativeai`): the new SDK is
client-based (`genai.Client(api_key=...)`), so each request's BYOK key gets its
own isolated client. The old SDK used a process-global `configure(api_key=...)`,
which is unsafe when concurrent requests carry different users' keys.
"""
from __future__ import annotations

from collections.abc import Sequence

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from .base import (
    BaseProvider,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
    retry_with_backoff,
)

# Free-tier-friendly defaults. Adjust here if Google changes model availability.
# (Verify against `python scripts/list_models.py` for a given key.)
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
# flash-LITE: purpose-built for low latency — the right pick for grounded RAG
# answers (we're extracting from provided context, not doing open-ended
# reasoning). Swap to a fuller model (e.g. "gemini-3.8-flash") if you want more
# answer quality at the cost of speed.
GEMINI_GENERATION_MODEL = "gemini-3.5-flash-lite"

# Reduced embedding size (Matryoshka). gemini-embedding-001 defaults to 3072
# dimensions; 768 keeps strong retrieval quality while cutting the embedding
# response payload and the vectors we store/compare ~4x, which trims both
# ingest and query latency. Cosine similarity is scale-invariant and Chroma
# uses cosine space, so no manual re-normalization is needed at this dimension.
GEMINI_EMBEDDING_DIM = 768


def _map_error(exc: Exception) -> ProviderError:
    """Map google-genai errors onto TabSage's normalized provider errors."""
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        detail = (getattr(exc, "message", None) or str(exc)).strip()
        if code in (401, 403):
            return ProviderAuthError("Invalid or unauthorized Gemini API key.")
        if code == 429:
            return ProviderRateLimit("Gemini rate limit hit.")
        if code in (408, 504):
            return ProviderTimeout("Gemini request timed out.")
        if code == 400:
            return ProviderBadRequest(f"Gemini rejected the request: {detail}")
        if isinstance(code, int) and code >= 500:
            return ProviderUnavailable("Gemini is temporarily unavailable.")
        return ProviderError(f"Gemini request failed ({code}): {detail}")
    # Network / connection issues without an HTTP code → treat as retryable.
    return ProviderUnavailable("Could not reach Gemini.")


class GeminiProvider(BaseProvider):
    provider_name = "gemini"
    embedding_model = GEMINI_EMBEDDING_MODEL
    generation_model = GEMINI_GENERATION_MODEL
    embedding_dim = GEMINI_EMBEDDING_DIM

    # Cap the answer length. Study answers rarely need more, and a smaller cap
    # means the model stops generating sooner → lower latency.
    max_output_tokens = 800

    # "thinking" disable. Sending thinking_budget=0 is the biggest latency win
    # on models that accept it, but some models reject the field (HTTP 400
    # "invalid argument"). gemini-3.5-flash-lite rejects it, so leave this None
    # (lite models barely use thinking anyway, so latency is already low). Only
    # set 0 on a full Flash model that accepts it.
    thinking_budget: int | None = None

    @property
    def embedding_model_id(self) -> str:
        # Include the output dimension: a session built at one dimension is not
        # comparable to vectors at another, so the store's consistency guard
        # must treat a dimension change like a model change.
        return f"{self.provider_name}:{self.embedding_model}@{self.embedding_dim}"

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        # One client per key (BYOK-safe). Construction does no network I/O.
        self._client = genai.Client(api_key=self._api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        config = genai_types.EmbedContentConfig(
            output_dimensionality=self.embedding_dim
        )
        out: list[list[float]] = []
        for start in range(0, len(items), self.embed_batch_size):
            batch = items[start : start + self.embed_batch_size]

            def call(batch: list[str] = batch) -> list[list[float]]:
                try:
                    resp = self._client.models.embed_content(
                        model=self.embedding_model, contents=batch, config=config
                    )
                    return [list(e.values) for e in resp.embeddings]
                except Exception as exc:  # noqa: BLE001 - normalized below
                    raise _map_error(exc) from exc

            out.extend(retry_with_backoff(call, max_attempts=self.max_retries))
        return out

    def generate(self, prompt: str) -> str:
        # We do not use tool/function calling, so disable AFC to avoid its
        # noisy "not recommended" warning and any extra round-trips. Cap the
        # output length and (optionally) disable thinking to cut latency.
        cfg_kwargs: dict = {
            "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            "max_output_tokens": self.max_output_tokens,
        }
        if self.thinking_budget is not None:
            cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=self.thinking_budget
            )
        config = genai_types.GenerateContentConfig(**cfg_kwargs)

        def call() -> str:
            try:
                resp = self._client.models.generate_content(
                    model=self.generation_model, contents=prompt, config=config
                )
                return resp.text or ""
            except Exception as exc:  # noqa: BLE001 - normalized below
                raise _map_error(exc) from exc

        return retry_with_backoff(call, max_attempts=self.max_retries)
