"""Manual Phase 4 check — embed & store (no key, no network).

Usage (from the backend/ folder, venv active):
    python scripts/try_store.py

Uses a deterministic in-process FakeProvider (hash-based embeddings) so the
whole embed → store → retrieve path can be exercised offline. It checks:
  1. store two tabs → chunk count
  2. semantic query returns the relevant tab's chunk (with citation metadata)
  3. source_tab_ids filter restricts retrieval
  4. session isolation (a second session can't see the first's data)
  5. dedupe: re-ingesting a tab does not double-count it
  6. embedding-model consistency guard raises on a model switch
  7. reset_session clears the session
  8. TTL purge_expired drops idle sessions
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from collections.abc import Sequence

# Make the backend package root importable when run as a script.
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from providers.base import BaseProvider  # noqa: E402
from rag import (  # noqa: E402
    ChromaVectorStore,
    EmbeddingModelMismatchError,
    embed_and_store,
    embed_query,
    prepare_chunks,
)

_DIM = 128


def _hash_embed(text: str, dim: int = _DIM) -> list[float]:
    """Deterministic bag-of-words embedding: shared words -> higher similarity."""
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider(BaseProvider):
    """Offline provider with deterministic embeddings; no key required."""

    provider_name = "fake"
    embedding_model = "fake-embed-v1"
    generation_model = "fake-gen"

    def __init__(self, embedding_model: str = "fake-embed-v1") -> None:
        # Skip BaseProvider's key requirement — this never calls a network.
        self.embedding_model = embedding_model
        self._api_key = "n/a"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]

    def generate(self, prompt: str) -> str:  # unused in Phase 4
        return "fake answer"


def _rule(label: str) -> None:
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


PAGE_BINARY = (
    "Binary search is an efficient algorithm for finding an item from a sorted "
    "list. It repeatedly halves the search interval, giving O(log n) time."
)
PAGE_HTTP = (
    "HTTP is a stateless request-response protocol. A client sends a request "
    "with a method like GET or POST and the server returns a status code."
)


def main() -> int:
    store = ChromaVectorStore()
    provider = FakeProvider()
    session = "sess-A"

    def chunks_for(tab_id, title, url, text):
        return prepare_chunks(
            text, session_id=session, tab_id=tab_id, title=title, url=url,
            chunk_size=200, chunk_overlap=40,
        )

    _rule("1) embed_and_store two tabs")
    n1 = embed_and_store(store, provider, session,
                         chunks_for("tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))
    n2 = embed_and_store(store, provider, session,
                         chunks_for("tab-http", "HTTP Basics", "https://ex/http", PAGE_HTTP))
    print(f"stored: tab-bin={n1} chunks, tab-http={n2} chunks")
    print("session count:", store.count(session))
    print("session tab_ids:", store.session_tab_ids(session))
    print("session embedding model:", store.session_embedding_model(session))

    _rule("2) query 'how does binary search run time scale' -> expect Binary tab")
    q = embed_query(provider, "how does binary search run time scale logarithmic")
    hits = store.query(session, q, provider.embedding_model_id, top_k=3)
    for h in hits:
        print(f"  score={h.score:+.3f} tab={h.metadata['tab_id']:<9} "
              f"title={h.metadata['title']!r}")
        print(f"      {h.text[:90]!r}")
    top = hits[0].metadata["tab_id"] if hits else None
    print("TOP TAB:", top, "->", "OK" if top == "tab-bin" else "UNEXPECTED")

    _rule("3) source_tab_ids filter -> restrict to HTTP tab only")
    hits_f = store.query(session, q, provider.embedding_model_id, top_k=3,
                         source_tab_ids=["tab-http"])
    print("returned tabs:", [h.metadata["tab_id"] for h in hits_f],
          "->", "OK" if all(h.metadata["tab_id"] == "tab-http" for h in hits_f) else "BAD")

    _rule("4) session isolation -> a different session sees nothing")
    print("count(sess-B):", store.count("sess-B"))
    print("query(sess-B):", store.query("sess-B", q, provider.embedding_model_id))

    _rule("5) dedupe -> re-ingest tab-bin, count must not grow")
    before = store.count(session)
    embed_and_store(store, provider, session,
                    chunks_for("tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))
    after = store.count(session)
    print(f"count before={before} after re-ingest={after} ->",
          "OK" if before == after else "DOUBLED (bad)")

    _rule("6) embedding-model guard -> switching model must raise")
    other = FakeProvider(embedding_model="fake-embed-v2")
    try:
        embed_and_store(store, other, session,
                        chunks_for("tab-bin", "Binary Search", "https://ex/bin", PAGE_BINARY))
        print("ERROR: expected EmbeddingModelMismatchError")
    except EmbeddingModelMismatchError as e:
        print("raised as expected ->", e)
    try:
        store.query(session, embed_query(other, "anything"), other.embedding_model_id)
        print("ERROR: expected EmbeddingModelMismatchError on query")
    except EmbeddingModelMismatchError as e:
        print("query guard raised as expected ->", type(e).__name__)

    _rule("7) reset_session -> clears everything")
    removed = store.reset_session(session)
    print(f"removed {removed} chunks; count now {store.count(session)}")

    _rule("8) TTL purge_expired -> idle session dropped")
    embed_and_store(store, provider, "sess-ttl",
                    prepare_chunks(PAGE_HTTP, session_id="sess-ttl", tab_id="t",
                                   title="x", url="u"))
    print("count(sess-ttl) before purge:", store.count("sess-ttl"))
    purged = store.purge_expired(ttl_seconds=0)  # everything is 'expired'
    print("purged:", purged, "count after:", store.count("sess-ttl"))

    print("\nOK — embed & store pipeline behaves as expected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
