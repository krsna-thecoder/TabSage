"""Embed + store orchestration (Phase 4).

Thin glue between the provider interface (which turns text into vectors using
the user's BYOK key) and the vector store (which persists them per session).
Kept separate from `store.py` so the store stays provider-agnostic and easy to
swap/test.

The user's key never appears here — it lives inside the provider instance,
which was built from the per-request key and is used transiently.
"""
from __future__ import annotations

from collections.abc import Sequence

from providers.base import BaseProvider

from .chunker import Chunk
from .store import VectorStore


def embed_and_store(
    store: VectorStore,
    provider: BaseProvider,
    session_id: str,
    chunks: Sequence[Chunk],
) -> int:
    """Embed `chunks` with `provider` and store them under `session_id`.

    Returns the number of chunks stored. Tags the session with the provider's
    `embedding_model_id` so the store can enforce embedding consistency; raises
    `EmbeddingModelMismatchError` (from the store) if the session already used a
    different model.
    """
    if not chunks:
        return 0
    embeddings = provider.embed([c.text for c in chunks])
    return store.add(session_id, list(chunks), embeddings, provider.embedding_model_id)


def embed_query(provider: BaseProvider, question: str) -> list[float]:
    """Embed a single query string, returning its vector."""
    vectors = provider.embed([question])
    return vectors[0] if vectors else []
