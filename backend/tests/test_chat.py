"""Chat / RAG tests (Phase 5) — grounded answers + honest refusals, offline."""
from __future__ import annotations

import pytest

from providers import (
    ProviderAuthError,
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
)
from rag import (
    NOT_IN_TABS,
    answer_question,
    build_prompt,
    describe_provider_error,
    embed_and_store,
    embed_query,
    prepare_chunks,
)

from ._fakes import FakeProvider

PAGE_BINARY = (
    "Binary search is an efficient algorithm for finding an item from a sorted "
    "list. It repeatedly halves the search interval, so its time complexity is "
    "O(log n), far better than a linear scan's O(n)."
)
PAGE_HTTP = (
    "HTTP is a stateless request-response protocol. A client sends a request "
    "with a method such as GET or POST, and the server replies with a status "
    "code like 200 OK or 404 Not Found."
)


def _seed(store, provider, session_id):
    for tab_id, title, url, text in [
        ("tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY),
        ("tab-http", "HTTP Basics", "https://ex/http", PAGE_HTTP),
    ]:
        chunks = prepare_chunks(text, session_id=session_id, tab_id=tab_id,
                                title=title, url=url)
        embed_and_store(store, provider, session_id, chunks)


def test_grounded_answer_has_citations(store, session_id):
    provider = FakeProvider(canned_answer="Binary search is O(log n) [1].")
    _seed(store, provider, session_id)
    res = answer_question(store, provider, session_id, "How fast is binary search?")
    assert res.grounded is True
    assert res.answer == "Binary search is O(log n) [1]."
    assert res.citations
    assert res.chunk_count >= 1
    # generate was called exactly once (the single answer).
    assert provider.generate_calls == 1


def test_citations_are_one_per_distinct_tab(store, session_id):
    provider = FakeProvider(canned_answer="See sources [1][2].")
    _seed(store, provider, session_id)
    res = answer_question(store, provider, session_id, "protocol and search",
                          top_k=5)
    tab_ids = [c.tab_id for c in res.citations]
    assert len(tab_ids) == len(set(tab_ids))  # no duplicate tabs


def test_no_retrieval_returns_refusal_without_generating(store, session_id):
    provider = FakeProvider(canned_answer="(should never be returned)")
    # Empty session → nothing retrieved.
    res = answer_question(store, provider, session_id, "anything at all?")
    assert res.grounded is False
    assert res.answer == NOT_IN_TABS
    assert res.citations == []
    assert provider.generate_calls == 0  # saved the generate call


def test_model_refusal_drops_citations(store, session_id):
    provider = FakeProvider(canned_answer=NOT_IN_TABS)
    _seed(store, provider, session_id)
    res = answer_question(store, provider, session_id, "capital of France?")
    assert res.grounded is False
    assert res.answer == NOT_IN_TABS
    assert res.citations == []
    assert res.chunk_count >= 1  # chunks were retrieved, model refused


def test_filter_to_nonexistent_tab_refuses(store, session_id):
    provider = FakeProvider()
    _seed(store, provider, session_id)
    res = answer_question(store, provider, session_id, "anything",
                          source_tab_ids=["does-not-exist"])
    assert res.grounded is False
    assert res.answer == NOT_IN_TABS


def test_empty_question_raises_value_error(store, session_id):
    provider = FakeProvider()
    _seed(store, provider, session_id)
    with pytest.raises(ValueError):
        answer_question(store, provider, session_id, "   ")


def test_build_prompt_contains_rules_sources_and_question(store, session_id):
    provider = FakeProvider()
    _seed(store, provider, session_id)
    hits = store.query(session_id, embed_query(provider, "binary search"),
                       provider.embedding_model_id, top_k=2)
    prompt = build_prompt("How fast is binary search?", hits)
    assert NOT_IN_TABS in prompt            # refusal instruction present
    assert "SOURCES:" in prompt
    assert "QUESTION: How fast is binary search?" in prompt
    assert "[1]" in prompt                  # numbered citation markers


@pytest.mark.parametrize(
    "exc, needle",
    [
        (ProviderAuthError("Invalid key."), "api key"),
        (ProviderRateLimit("Rate limited."), "rate limit"),
        (ProviderTimeout("Timed out."), "timed out"),
        (ProviderUnavailable("Down."), "unavailable"),
    ],
)
def test_describe_provider_error_adds_hint(exc, needle):
    msg = describe_provider_error(exc).lower()
    assert needle in msg
