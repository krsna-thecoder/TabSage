"""TabSage RAG pipeline.

Phase 3 (INGEST — clean & chunk) public API:
    clean_text(raw) -> str
    Chunk, chunk_text(...) -> list[Chunk]
    prepare_chunks(...) -> list[Chunk]        # clean + chunk + payload caps
    Errors: IngestError, EmptyContentError, PayloadTooLargeError

Modules added in later phases: store.py (Phase 4), chat.py (Phase 5).
"""
from __future__ import annotations

from .chunker import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    Chunk,
    chunk_text,
)
from .clean import clean_text
from .errors import EmptyContentError, IngestError, PayloadTooLargeError
from .ingest import prepare_chunks

__all__ = [
    "clean_text",
    "Chunk",
    "chunk_text",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "prepare_chunks",
    "IngestError",
    "EmptyContentError",
    "PayloadTooLargeError",
]
