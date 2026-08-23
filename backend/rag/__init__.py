"""TabSage RAG pipeline.

Phase 3 (INGEST — clean & chunk):
    clean_text(raw) -> str
    Chunk, chunk_text(...) -> list[Chunk]
    prepare_chunks(...) -> list[Chunk]        # clean + chunk + payload caps
    Errors: IngestError, EmptyContentError, PayloadTooLargeError

Phase 4 (EMBED & STORE):
    VectorStore, ChromaVectorStore, get_store()
    Retrieved, DEFAULT_TOP_K
    embed_and_store(store, provider, session_id, chunks) -> int
    embed_query(provider, question) -> list[float]
    Errors: StoreError, EmbeddingModelMismatchError

Phase 5 (RETRIEVE & GENERATE):
    answer_question(store, provider, session_id, question, ...) -> ChatResult
    build_prompt(question, hits) -> str
    Citation, ChatResult, NOT_IN_TABS, describe_provider_error
"""
from __future__ import annotations

from .chat import (
    NOT_IN_TABS,
    Citation,
    ChatResult,
    answer_question,
    build_prompt,
    describe_provider_error,
)
from .chunker import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    Chunk,
    chunk_text,
)
from .clean import clean_text
from .errors import EmptyContentError, IngestError, PayloadTooLargeError
from .index import embed_and_store, embed_query
from .ingest import prepare_chunks
from .store import (
    DEFAULT_TOP_K,
    ChromaVectorStore,
    EmbeddingModelMismatchError,
    Retrieved,
    StoreError,
    VectorStore,
    get_store,
)

__all__ = [
    # Phase 3 — ingest
    "clean_text",
    "Chunk",
    "chunk_text",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "prepare_chunks",
    "IngestError",
    "EmptyContentError",
    "PayloadTooLargeError",
    # Phase 4 — embed & store
    "VectorStore",
    "ChromaVectorStore",
    "get_store",
    "Retrieved",
    "DEFAULT_TOP_K",
    "embed_and_store",
    "embed_query",
    "StoreError",
    "EmbeddingModelMismatchError",
    # Phase 5 — retrieve & generate
    "answer_question",
    "build_prompt",
    "Citation",
    "ChatResult",
    "NOT_IN_TABS",
    "describe_provider_error",
]
