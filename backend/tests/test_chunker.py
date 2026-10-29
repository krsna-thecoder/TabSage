"""Unit tests for rag.chunker.chunk_text (Phase 3)."""
from __future__ import annotations

import pytest

from rag import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, Chunk, chunk_text

META = dict(
    session_id="s1",
    tab_id="tab-1",
    title="T",
    url="https://ex/t",
)


def test_empty_input_yields_no_chunks():
    assert chunk_text("", **META) == []
    assert chunk_text("   \n\n  ", **META) == []


def test_tiny_text_is_single_chunk():
    chunks = chunk_text("Just one short line.", **META)
    assert len(chunks) == 1
    assert chunks[0].text == "Just one short line."


def test_metadata_attached_to_every_chunk():
    text = "word " * 2000  # forces multiple chunks
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40, **META)
    assert len(chunks) > 1
    for i, c in enumerate(chunks):
        assert isinstance(c, Chunk)
        assert c.metadata["session_id"] == "s1"
        assert c.metadata["tab_id"] == "tab-1"
        assert c.metadata["title"] == "T"
        assert c.metadata["url"] == "https://ex/t"
        # chunk_index is 0-based and contiguous.
        assert c.metadata["chunk_index"] == i


def test_no_chunk_exceeds_chunk_size():
    text = "word " * 2000
    size = 200
    chunks = chunk_text(text, chunk_size=size, chunk_overlap=40, **META)
    for c in chunks:
        assert len(c.text) <= size


def test_smaller_chunk_size_produces_more_chunks():
    text = "word " * 2000
    few = chunk_text(text, chunk_size=400, chunk_overlap=40, **META)
    many = chunk_text(text, chunk_size=100, chunk_overlap=20, **META)
    assert len(many) > len(few)


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_text("some text here", chunk_size=100, chunk_overlap=100, **META)


def test_default_tuning_constants():
    assert DEFAULT_CHUNK_SIZE == 800
    assert DEFAULT_CHUNK_OVERLAP == 150
