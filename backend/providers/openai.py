"""OpenAI provider (optional) — uses the `openai` SDK.

Note: `import openai` here resolves to the installed top-level SDK, not this
sibling module (Python 3 uses absolute imports), so the filename is safe.
"""
from __future__ import annotations

from collections.abc import Sequence

import openai
from openai import OpenAI

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

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_GENERATION_MODEL = "gpt-4o-mini"


def _map_error(exc: Exception) -> ProviderError:
    """Map openai errors onto TabSage's normalized provider errors."""
    if isinstance(exc, openai.AuthenticationError):
        return ProviderAuthError("Invalid or unauthorized OpenAI API key.")
    if isinstance(exc, openai.PermissionDeniedError):
        return ProviderAuthError("OpenAI API key lacks permission for this resource.")
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimit("OpenAI rate limit hit.")
    if isinstance(exc, openai.APITimeoutError):
        return ProviderTimeout("OpenAI request timed out.")
    if isinstance(exc, openai.BadRequestError):
        return ProviderBadRequest("OpenAI rejected the request (bad input or model).")
    if isinstance(exc, (openai.InternalServerError, openai.APIConnectionError)):
        return ProviderUnavailable("OpenAI is temporarily unavailable.")
    if isinstance(exc, openai.APIStatusError):
        code = getattr(exc, "status_code", None)
        if code == 429:
            return ProviderRateLimit("OpenAI rate limit hit.")
        if isinstance(code, int) and code >= 500:
            return ProviderUnavailable("OpenAI is temporarily unavailable.")
    return ProviderError("OpenAI request failed.")


class OpenAIProvider(BaseProvider):
    provider_name = "openai"
    embedding_model = OPENAI_EMBEDDING_MODEL
    generation_model = OPENAI_GENERATION_MODEL

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        # One client per key (BYOK-safe). Construction does no network I/O.
        self._client = OpenAI(api_key=self._api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        out: list[list[float]] = []
        for start in range(0, len(items), self.embed_batch_size):
            batch = items[start : start + self.embed_batch_size]

            def call(batch: list[str] = batch) -> list[list[float]]:
                try:
                    resp = self._client.embeddings.create(
                        model=self.embedding_model, input=batch
                    )
                    return [d.embedding for d in resp.data]
                except Exception as exc:  # noqa: BLE001 - normalized below
                    raise _map_error(exc) from exc

            out.extend(retry_with_backoff(call, max_attempts=self.max_retries))
        return out

    def generate(self, prompt: str) -> str:
        def call() -> str:
            try:
                resp = self._client.chat.completions.create(
                    model=self.generation_model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - normalized below
                raise _map_error(exc) from exc

        return retry_with_backoff(call, max_attempts=self.max_retries)
