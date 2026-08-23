"""INGEST pipeline: raw page text → clean → chunk, with hard limits (Phase 3).

`prepare_chunks` is the single entry point the API endpoint (Phase 6) will call
before embedding + storing. It enforces the server-side payload caps from
Section 10 and normalizes the edge cases so the endpoint layer only has to map
`IngestError` subclasses onto HTTP responses.

Order of operations (limits first = fail fast, cheapest checks first):
  1. Size cap on the *raw* text (`max_text_chars`)  -> PayloadTooLargeError
  2. Clean the text                                  -> may become empty
  3. Empty-after-clean guard                          -> EmptyContentError
  4. Chunk with source metadata
  5. Chunk-count cap (`max_chunks`)                   -> PayloadTooLargeError

Note on `max_sources_per_session`: that cap is per session and needs knowledge
of what's already stored, so it is enforced at the store/endpoint layer
(Phases 4/6), not here where we only see one page.
"""
from __future__ import annotations

from config import settings

from .chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, Chunk, chunk_text
from .clean import clean_text
from .errors import EmptyContentError, PayloadTooLargeError


def prepare_chunks(
    raw_text: str,
    *,
    session_id: str,
    tab_id: str,
    title: str,
    url: str,
    max_text_chars: int | None = None,
    max_chunks: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Clean + chunk `raw_text`, enforcing payload caps.

    Args:
        raw_text: The page text extracted by the extension (`innerText`).
        session_id, tab_id, title, url: Source metadata attached to each chunk.
        max_text_chars: Raw-text size cap. Defaults to `settings.max_text_chars`.
        max_chunks: Chunk-count cap. Defaults to `settings.max_chunks_per_ingest`.
        chunk_size, chunk_overlap: Splitter tuning.

    Returns:
        A non-empty list of `Chunk`s ready to embed + store.

    Raises:
        PayloadTooLargeError: raw text or chunk count exceeds its cap.
        EmptyContentError: nothing usable remained after cleaning.
    """
    text_cap = settings.max_text_chars if max_text_chars is None else max_text_chars
    chunk_cap = settings.max_chunks_per_ingest if max_chunks is None else max_chunks

    # 1. Reject oversized pages before doing any work.
    raw_len = len(raw_text or "")
    if raw_len > text_cap:
        raise PayloadTooLargeError(
            f"Page text is too large: {raw_len} chars (limit {text_cap})."
        )

    # 2–3. Clean, then reject pages that were empty or all boilerplate.
    cleaned = clean_text(raw_text)
    if not cleaned:
        raise EmptyContentError("No usable text after cleaning the page.")

    # 4. Chunk with source metadata.
    chunks = chunk_text(
        cleaned,
        session_id=session_id,
        tab_id=tab_id,
        title=title,
        url=url,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not chunks:
        # Defensive: non-empty cleaned text should always yield >= 1 chunk.
        raise EmptyContentError("Page produced no chunks.")

    # 5. Reject pages that explode into too many chunks.
    if len(chunks) > chunk_cap:
        raise PayloadTooLargeError(
            f"Page produced too many chunks: {len(chunks)} (limit {chunk_cap})."
        )

    return chunks
