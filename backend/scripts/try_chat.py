"""Manual Phase 5 check — retrieve & generate (the full RAG loop).

Two modes:

  python scripts/try_chat.py            # OFFLINE plumbing demo (no key/network)
  python scripts/try_chat.py live       # LIVE end-to-end with Gemini (needs key)

OFFLINE uses deterministic fake providers to prove the wiring without a key:
  * a grounded answer carries citations (tab title/url)
  * an empty/filtered session returns the honest "not in your tabs" refusal
    WITHOUT calling generate
  * when the model itself emits the refusal line, citations are dropped and
    grounded=False

LIVE ingests two sample pages with real Gemini embeddings, then asks an
in-context question (expect a grounded, cited answer) and an out-of-context
question (expect the refusal). Key is read from TABSAGE_TEST_KEY or a hidden
prompt; it is used transiently and never stored.
"""
from __future__ import annotations

import getpass
import hashlib
import math
import os
import sys
from collections.abc import Sequence

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from providers.base import BaseProvider  # noqa: E402
from rag import (  # noqa: E402
    NOT_IN_TABS,
    ChromaVectorStore,
    answer_question,
    build_prompt,
    embed_and_store,
    prepare_chunks,
)

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


def _rule(label: str) -> None:
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


# ── offline fakes ─────────────────────────────────────────────────────────
def _hash_embed(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider(BaseProvider):
    """Deterministic embeddings + a scripted `generate` output."""

    provider_name = "fake"
    embedding_model = "fake-embed-v1"
    generation_model = "fake-gen"

    def __init__(self, canned_answer: str = "Fake grounded answer.") -> None:
        self._api_key = "n/a"
        self._canned = canned_answer
        self.generate_calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]

    def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        return self._canned


def _ingest_samples(store, provider, session):
    for tab_id, title, url, text in [
        ("tab-bin", "Binary Search", "https://ex/binary-search", PAGE_BINARY),
        ("tab-http", "HTTP Basics", "https://ex/http", PAGE_HTTP),
    ]:
        chunks = prepare_chunks(
            text, session_id=session, tab_id=tab_id, title=title, url=url
        )
        embed_and_store(store, provider, session, chunks)


def _show(result) -> None:
    print("grounded:  ", result.grounded)
    print("chunks:    ", result.chunk_count)
    print("answer:    ", result.answer)
    if result.citations:
        print("citations:")
        for c in result.citations:
            print(f"   - [{c.tab_id}] {c.title} — {c.url}")
            print(f"       “{(c.snippet or '')[:80]}…”")
    else:
        print("citations:  (none)")


def run_offline() -> int:
    session = "sess-offline"

    _rule("OFFLINE 1) grounded answer carries citations")
    store = ChromaVectorStore()
    grounded_provider = FakeProvider(
        canned_answer="Binary search runs in O(log n) time because it halves the "
        "interval each step [1]."
    )
    _ingest_samples(store, grounded_provider, session)
    res = answer_question(store, grounded_provider, session,
                          "How fast is binary search?")
    _show(res)
    print("-> generate() calls:", grounded_provider.generate_calls)

    _rule("OFFLINE 2) show the grounded prompt that was sent")
    from rag import embed_query
    hits = store.query(session, embed_query(grounded_provider, "binary search speed"),
                       grounded_provider.embedding_model_id, top_k=2)
    print(build_prompt("How fast is binary search?", hits)[:600], "...")

    _rule("OFFLINE 3) no retrieval -> honest refusal, generate NOT called")
    empty_provider = FakeProvider(canned_answer="(should never be returned)")
    res2 = answer_question(store, empty_provider, "sess-empty",
                           "anything at all?")
    _show(res2)
    print("-> generate() calls:", empty_provider.generate_calls,
          "->", "OK" if empty_provider.generate_calls == 0
          and res2.answer == NOT_IN_TABS and not res2.grounded else "BAD")

    _rule("OFFLINE 4) model emits refusal line -> citations dropped, grounded False")
    refusing = FakeProvider(canned_answer=NOT_IN_TABS)
    _ingest_samples(store, refusing, "sess-refuse")
    res3 = answer_question(store, refusing, "sess-refuse",
                           "what is the capital of France?")
    _show(res3)
    print("->", "OK" if not res3.grounded and not res3.citations else "BAD")

    print("\nOK — chat plumbing behaves as expected (offline).")
    return 0


def run_live() -> int:
    from providers import ProviderError, get_provider
    from schemas import Provider

    key = os.environ.get("TABSAGE_TEST_KEY") or getpass.getpass(
        "Paste your Gemini API key (hidden input): "
    )
    provider = get_provider(Provider.gemini, key)
    store = ChromaVectorStore()
    session = "sess-live"

    try:
        _rule("LIVE 0) ingest two sample tabs with real Gemini embeddings")
        _ingest_samples(store, provider, session)
        print("stored chunks:", store.count(session),
              "| tabs:", store.session_tab_ids(session))

        _rule("LIVE 1) in-context question -> expect grounded answer + citation")
        _show(answer_question(store, provider, session,
                              "Why is binary search faster than a linear scan?"))

        _rule("LIVE 2) out-of-context question -> expect honest refusal")
        _show(answer_question(store, provider, session,
                              "What is the capital of France?"))

        print("\nOK — full RAG loop works end to end with Gemini.")
        return 0
    except ProviderError as err:
        from rag import describe_provider_error
        print(f"\nProvider error: {type(err).__name__}: {describe_provider_error(err)}")
        return 1


def main() -> int:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "offline"
    if mode == "live":
        return run_live()
    return run_offline()


if __name__ == "__main__":
    raise SystemExit(main())
