"""Provider factory — pick the implementation from the request's `provider`.

Swapping providers is a config choice, not a code change: everything downstream
depends only on `BaseProvider`.
"""
from __future__ import annotations

from schemas import Provider

from .base import BaseProvider, ProviderError
from .gemini import GeminiProvider
from .openai import OpenAIProvider

_REGISTRY: dict[Provider, type[BaseProvider]] = {
    Provider.gemini: GeminiProvider,
    Provider.openai: OpenAIProvider,
}


def get_provider(provider: Provider, api_key: str) -> BaseProvider:
    """Build a provider instance for `provider`, using the per-request key.

    The key is used transiently by the returned instance and never persisted.
    """
    impl = _REGISTRY.get(provider)
    if impl is None:
        raise ProviderError(f"Unsupported provider: {provider!r}")
    return impl(api_key)
