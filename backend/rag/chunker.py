"""Split cleaned page text into overlapping, retrievable chunks (Phase 3).

Uses LangChain's `RecursiveCharacterTextSplitter`, which tries to break on the
most natural boundary available (paragraph → line → sentence → word) before
falling back to a hard character cut. That keeps most chunks semantically whole.

Why ~800 chars / ~150 overlap:
  * 800 characters is roughly a paragraph or two — big enough to carry a
    self-contained idea, small enough that a single chunk stays on-topic and
    embeds precisely. Oversized chunks blur meaning and hurt retrieval.
  * 150 characters of overlap (~one or two sentences) means a concept that
    straddles a boundary still appears whole in at least one chunk, so
    retrieval doesn't miss an answer that happens to land on a chunk edge.
These are defaults; they're tunable in Phase 11 against a small eval set.

Each chunk carries the metadata needed downstream for storage, session
isolation, and citations: `session_id`, `tab_id`, `title`, `url`, plus a
`chunk_index` for stable ordering/debugging. The embedding-model id is attached
later at embed/store time (Phase 4), not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Defaults (characters). See module docstring for the rationale.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150

# Preferred split boundaries, most-natural first. The empty string is the final
# hard fallback so no chunk can ever exceed `chunk_size`.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage plus the metadata stored alongside its vector."""

    text: str
    metadata: dict[str, Any]


def chunk_text(
    text: str,
    *,
    session_id: str,
    tab_id: str,
    title: str,
    url: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split `text` into overlapping `Chunk`s with source metadata.

    Returns an empty list for empty/whitespace-only input (a tiny page yields a
    single chunk). Metadata on every chunk: session_id, tab_id, title, url,
    chunk_index (0-based, contiguous over the returned chunks).
    """
    if not text or not text.strip():
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARATORS,
        length_function=len,
        keep_separator=True,
    )

    pieces = [p.strip() for p in splitter.split_text(text)]
    pieces = [p for p in pieces if p]  # drop any empties left by stripping

    return [
        Chunk(
            text=piece,
            metadata={
                "session_id": session_id,
                "tab_id": tab_id,
                "title": title,
                "url": url,
                "chunk_index": index,
            },
        )
        for index, piece in enumerate(pieces)
    ]
