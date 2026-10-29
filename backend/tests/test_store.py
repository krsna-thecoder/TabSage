"""Vector-store tests (Phase 4) — offline, deterministic FakeProvider."""
from __future__ import annotations

import pytest

from rag import (
    EmbeddingModelMismatchError,
    StoreError,
    embed_and_store,
    embed_query,
    prepare_chunks,
)

from ._fakes import FakeProvider

PAGE_BINARY = (
    "Binary search is an efficient algorithm for finding an item from a sorted "
    "list. It repeatedly halves the search interval, giving O(log n) time."
)
PAGE_HTTP = (
    "HTTP is a stateless request-response protocol. A client sends a request "
    "with a method like GET or POST and the server returns a status code."
)


def _chunks(session_id, tab_id, title, url, text):
    return prepare_chunks(
        text, session_id=session_id, tab_id=tab_id, title=title, url=url,
        chunk_size=200, chunk_overlap=40,
    )


def _seed(store, provider, session_id):
    embed_and_store(store, provider, session_id,
                    _chunks(session_id, "tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))
    embed_and_store(store, provider, session_id,
                    _chunks(session_id, "tab-http", "HTTP Basics", "https://ex/http", PAGE_HTTP))


def test_store_and_count(store, provider, session_id):
    _seed(store, provider, session_id)
    assert store.count(session_id) == 2
    assert set(store.session_tab_ids(session_id)) == {"tab-bin", "tab-http"}
    assert store.session_embedding_model(session_id) == "fake:fake-embed-v1"


def test_query_returns_most_relevant_tab(store, provider, session_id):
    _seed(store, provider, session_id)
    q = embed_query(provider, "how does binary search run time scale logarithmic")
    hits = store.query(session_id, q, provider.embedding_model_id, top_k=3)
    assert hits
    assert hits[0].metadata["tab_id"] == "tab-bin"
    # score is a cosine similarity recovered from distance.
    assert -1.0 <= hits[0].score <= 1.0


def test_source_tab_ids_filter_restricts_retrieval(store, provider, session_id):
    _seed(store, provider, session_id)
    q = embed_query(provider, "binary search logarithmic time")
    hits = store.query(session_id, q, provider.embedding_model_id, top_k=3,
                       source_tab_ids=["tab-http"])
    assert hits
    assert all(h.metadata["tab_id"] == "tab-http" for h in hits)


def test_session_isolation(store, provider, session_id):
    _seed(store, provider, session_id)
    q = embed_query(provider, "anything")
    assert store.count("other-session") == 0
    assert store.query("other-session", q, provider.embedding_model_id) == []


def test_query_empty_session_returns_empty(store, provider, session_id):
    q = embed_query(provider, "anything")
    assert store.query(session_id, q, provider.embedding_model_id) == []


def test_dedupe_reingest_does_not_grow(store, provider, session_id):
    _seed(store, provider, session_id)
    before = store.count(session_id)
    embed_and_store(store, provider, session_id,
                    _chunks(session_id, "tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))
    assert store.count(session_id) == before


def test_model_mismatch_guard_on_add(store, provider, session_id):
    _seed(store, provider, session_id)
    other = FakeProvider(embedding_model="fake-embed-v2")
    with pytest.raises(EmbeddingModelMismatchError):
        embed_and_store(store, other, session_id,
                        _chunks(session_id, "tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))


def test_model_mismatch_guard_on_query(store, provider, session_id):
    _seed(store, provider, session_id)
    other = FakeProvider(embedding_model="fake-embed-v2")
    with pytest.raises(EmbeddingModelMismatchError):
        store.query(session_id, embed_query(other, "x"), other.embedding_model_id)


def test_reset_session_clears(store, provider, session_id):
    _seed(store, provider, session_id)
    removed = store.reset_session(session_id)
    assert removed == 2
    assert store.count(session_id) == 0
    assert store.session_embedding_model(session_id) is None


def test_delete_tab_removes_only_that_tab(store, provider, session_id):
    _seed(store, provider, session_id)
    removed = store.delete_tab(session_id, "tab-bin")
    assert removed == 1
    assert store.session_tab_ids(session_id) == ["tab-http"]


def test_purge_expired_drops_idle_sessions(store, provider, session_id):
    _seed(store, provider, session_id)
    purged = store.purge_expired(ttl_seconds=0)  # everything counts as expired
    assert session_id in purged
    assert store.count(session_id) == 0


def test_add_length_mismatch_raises(store, provider, session_id):
    chunks = _chunks(session_id, "tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY)
    # Deliberately supply more embeddings than chunks.
    with pytest.raises(StoreError):
        store.add(session_id, chunks, [[0.1], [0.2]], provider.embedding_model_id)
