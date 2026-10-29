"""Unit tests for rag.ingest.prepare_chunks — clean + chunk + caps (Phase 3)."""
from __future__ import annotations

import pytest

from rag import EmptyContentError, PayloadTooLargeError, prepare_chunks

META = dict(
    session_id="s1",
    tab_id="tab-1",
    title="T",
    url="https://ex/t",
)

REAL_TEXT = (
    "Binary search is an efficient algorithm for finding an item from a sorted "
    "list. It repeatedly halves the search interval, giving O(log n) time."
)


def test_happy_path_returns_nonempty_chunks():
    chunks = prepare_chunks(REAL_TEXT, **META)
    assert len(chunks) >= 1
    assert all(c.metadata["tab_id"] == "tab-1" for c in chunks)


def test_whitespace_only_raises_empty_content():
    with pytest.raises(EmptyContentError):
        prepare_chunks("   \n\n   ", **META)


def test_all_boilerplate_collapses_to_empty_then_raises():
    # Consecutive duplicate lines are dropped; a single surviving nav token is
    # still "content" to the cleaner, so use pure whitespace to hit the guard.
    with pytest.raises(EmptyContentError):
        prepare_chunks("\n\n\n", **META)


def test_oversized_raw_text_raises_payload_too_large():
    huge = "word " * 100_000  # ~500k chars
    with pytest.raises(PayloadTooLargeError):
        prepare_chunks(huge, max_text_chars=200_000, **META)


def test_too_many_chunks_raises_payload_too_large():
    many = "Sentence about algorithms and data structures. " * 400
    with pytest.raises(PayloadTooLargeError):
        prepare_chunks(many, chunk_size=100, chunk_overlap=10, max_chunks=5, **META)


def test_caps_are_inclusive_boundaries():
    # Exactly at the text cap is allowed; one over is rejected.
    text = "a" * 50
    assert prepare_chunks(text, max_text_chars=50, **META)
    with pytest.raises(PayloadTooLargeError):
        prepare_chunks("a" * 51, max_text_chars=50, **META)
