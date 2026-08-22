"""TabSage provider abstraction (BYOK core).

Public API:
    get_provider(provider, api_key) -> BaseProvider
    BaseProvider, GeminiProvider, OpenAIProvider
    Provider errors: ProviderError, ProviderAuthError, ProviderBadRequest,
        ProviderRateLimit, ProviderTimeout, ProviderUnavailable
"""
from __future__ import annotations

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
from .factory import get_provider
from .gemini import GeminiProvider
from .openai import OpenAIProvider

__all__ = [
    "get_provider",
    "BaseProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "ProviderError",
    "ProviderAuthError",
    "ProviderBadRequest",
    "ProviderRateLimit",
    "ProviderTimeout",
    "ProviderUnavailable",
    "retry_with_backoff",
]
