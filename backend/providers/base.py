"""Provider interface for TabSage (the BYOK core).

A provider wraps one AI vendor behind two methods: `embed(texts)` and
`generate(prompt)`. Everything downstream (chunk store, chat) depends only on
this interface, so swapping providers is a config choice, not a code change.

Key handling: the per-request user key is passed to the constructor and held
only in memory for the life of the instance. It is NEVER logged, persisted, or
placed in `__repr__`.
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


# ── Normalized provider errors ────────────────────────────────────────────
# Concrete providers map vendor-specific exceptions onto these, so upstream
# code (Phase 5 chat) can produce friendly, specific messages without knowing
# which vendor was used. Messages must never contain key material.

class ProviderError(Exception):
    """Base class for all provider errors."""


class ProviderAuthError(ProviderError):
    """Bad / expired / unauthorized API key (HTTP 401/403). Not retryable."""


class ProviderBadRequest(ProviderError):
    """Malformed request, e.g. bad model name or input (HTTP 400). Not retryable."""


class ProviderRateLimit(ProviderError):
    """Rate limited (HTTP 429). Retryable with backoff."""


class ProviderTimeout(ProviderError):
    """Request timed out (HTTP 408/504 or client timeout). Retryable."""


class ProviderUnavailable(ProviderError):
    """Provider 5xx or connection failure. Retryable."""


# Errors worth retrying with exponential backoff.
RETRYABLE: tuple[type[ProviderError], ...] = (
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn`, retrying on RETRYABLE provider errors with exponential
    backoff + jitter. Re-raises the last error after `max_attempts`.

    Ingesting one page produces many embedding calls, which can trip free-tier
    per-minute limits; this smooths those bursts (Section 9 rate-limit guard).
    """
    last_err: ProviderError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except RETRYABLE as err:
            last_err = err
            if attempt == max_attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter
            sleep(delay)
    assert last_err is not None
    raise last_err


class BaseProvider(ABC):
    """Abstract provider. Subclasses set the model names and implement calls."""

    provider_name: str = "base"
    embedding_model: str = ""
    generation_model: str = ""

    # Batch size for embedding calls (bounds request size + smooths rate limits).
    embed_batch_size: int = 100
    # Retry attempts for transient provider errors. Kept low + short-backoff
    # (see retry_with_backoff defaults) so a rate-limited call fails fast with a
    # friendly 429 instead of hanging ~30s on exponential sleeps — important for
    # chat latency.
    max_retries: int = 4

    def __init__(self, api_key: str) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ProviderAuthError("Missing API key.")
        # Transient, in-memory only. Never logged or persisted.
        self._api_key = key

    @property
    def embedding_model_id(self) -> str:
        """Stable id stored in every chunk's metadata for the embedding-
        consistency guard (Sections 6 & 9). A query whose provider/model id
        does not match the session's stored id must be refused / auto-reset,
        because embeddings from different models are not comparable.
        """
        return f"{self.provider_name}:{self.embedding_model}"

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text (order preserved)."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the model's text completion for `prompt`."""

    def __repr__(self) -> str:  # never expose the key
        return (
            f"<{type(self).__name__} provider={self.provider_name!r} "
            f"embedding={self.embedding_model!r} generation={self.generation_model!r}>"
        )
