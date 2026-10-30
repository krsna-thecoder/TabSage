"""RETRIEVE & GENERATE — grounded question answering (Phase 5).

The heart of the RAG loop. Given a question and a session's stored chunks:

    embed the question  ->  retrieve top-K chunks  ->  build a grounded prompt
    ->  generate with the provider  ->  return {answer, citations}

Two invariants make TabSage trustworthy:

* **Grounded generation.** The prompt instructs the model to answer using ONLY
  the retrieved sources and to fall back to a fixed refusal sentence when the
  answer isn't there. This is how we avoid hallucination — the whole product
  promise is "answers from *your* tabs, or an honest 'not found'".

* **Honest "not in your tabs".** If retrieval returns nothing (empty session,
  or a `source_tab_ids` filter that matches no chunks), we return the refusal
  immediately WITHOUT spending a generate call. If the model itself decides the
  answer isn't present, it emits the same refusal sentence and we drop the
  citations. Either way `ChatResult.grounded` is False.

Errors: `provider.embed` / `provider.generate` raise already-normalized,
key-free `ProviderError`s (auth/rate-limit/timeout/…); `store.query` may raise
`EmbeddingModelMismatchError`. Both are allowed to propagate so the API layer
(Phase 6) can map them to specific HTTP responses. `describe_provider_error`
gives a friendly one-liner for logs/UX without leaking internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from providers.base import (
    BaseProvider,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
)

from .index import embed_query
from .store import DEFAULT_TOP_K, Retrieved, VectorStore

# The exact sentence the model must emit (and that we return) when the answer
# is not supported by the retrieved sources. Kept as a constant so the prompt
# and the detection logic can never drift apart.
NOT_IN_TABS = "I couldn't find that in your selected tabs."

# How much of a chunk to echo back as a citation snippet.
_SNIPPET_CHARS = 220


@dataclass(frozen=True)
class Citation:
    """A source backing an answer (one per distinct tab, retrieval order)."""

    tab_id: str
    title: str
    url: str
    snippet: str | None = None


@dataclass(frozen=True)
class ChatResult:
    """The outcome of one question."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    # True when the answer came from the sources; False for either flavour of
    # "not in your tabs" (no retrieval, or the model refused).
    grounded: bool = True
    # Number of chunks retrieved and shown to the model (debug/telemetry).
    chunk_count: int = 0


def _norm(text: str) -> str:
    """Loose comparison form: lowercased, trailing punctuation/space removed."""
    return text.strip().rstrip(".!").strip().lower()


def _snippet(text: str) -> str:
    text = text.strip()
    if len(text) <= _SNIPPET_CHARS:
        return text
    return text[:_SNIPPET_CHARS].rstrip() + "…"


def build_prompt(question: str, hits: list[Retrieved]) -> str:
    """Assemble the grounded RAG prompt from retrieved chunks."""
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.metadata.get("title") or "Untitled"
        url = h.metadata.get("url") or ""
        header = f"[{i}] {title}".rstrip()
        if url:
            header += f" — {url}"
        blocks.append(f"{header}\n{h.text.strip()}")
    context = "\n\n".join(blocks)

    return (
        "You are TabSage, a study assistant. Answer the QUESTION using ONLY the "
        "information in the SOURCES below. Do not use any outside knowledge and "
        "do not guess.\n"
        "Keep the answer concise and direct — a few sentences at most.\n"
        f'If the SOURCES do not contain the answer, reply with exactly this '
        f'sentence and nothing else:\n"{NOT_IN_TABS}"\n'
        "When you use a source, cite it inline with its bracket number, e.g. [1].\n\n"
        f"SOURCES:\n{context}\n\n"
        f"QUESTION: {question}\n\n"
        "ANSWER:"
    )


def _citations(hits: list[Retrieved]) -> list[Citation]:
    """One citation per distinct tab, preserving retrieval order."""
    out: list[Citation] = []
    seen: set[str] = set()
    for h in hits:
        tab_id = str(h.metadata.get("tab_id") or "")
        if tab_id in seen:
            continue
        seen.add(tab_id)
        out.append(
            Citation(
                tab_id=tab_id,
                title=str(h.metadata.get("title") or ""),
                url=str(h.metadata.get("url") or ""),
                snippet=_snippet(h.text),
            )
        )
    return out


def answer_question(
    store: VectorStore,
    provider: BaseProvider,
    session_id: str,
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    source_tab_ids: list[str] | None = None,
) -> ChatResult:
    """Answer `question` from a session's stored tabs, grounded + cited.

    Raises:
        ValueError: if `question` is empty/blank.
        ProviderError (subclass): embed/generate failed (bad key, rate limit…).
        EmbeddingModelMismatchError: the session was built with another model.
    """
    q = (question or "").strip()
    if not q:
        raise ValueError("Question must not be empty.")

    # Embed the question with the SAME provider/model the session was built
    # with; the store enforces that and raises on mismatch.
    q_vec = embed_query(provider, q)
    hits = store.query(
        session_id,
        q_vec,
        provider.embedding_model_id,
        top_k=top_k,
        source_tab_ids=source_tab_ids,
    )

    # Honest refusal #1: nothing retrieved → don't spend a generate call.
    if not hits:
        return ChatResult(answer=NOT_IN_TABS, citations=[], grounded=False, chunk_count=0)

    prompt = build_prompt(q, hits)
    raw = provider.generate(prompt)
    answer = (raw or "").strip()

    # Honest refusal #2: empty output, or the model emitted the refusal line.
    if not answer or _norm(answer) == _norm(NOT_IN_TABS):
        return ChatResult(
            answer=NOT_IN_TABS, citations=[], grounded=False, chunk_count=len(hits)
        )

    return ChatResult(
        answer=answer,
        citations=_citations(hits),
        grounded=True,
        chunk_count=len(hits),
    )


def describe_provider_error(exc: ProviderError) -> str:
    """A friendly, specific one-liner for a normalized provider error.

    The provider layer already produces key-free messages; this adds a short
    actionable hint. Used by the API layer (Phase 6) and manual scripts.
    """
    hint = {
        ProviderAuthError: "Check that your API key is correct and active.",
        ProviderRateLimit: "You've hit the provider's rate limit — wait and retry.",
        ProviderTimeout: "The provider timed out — try again.",
        ProviderUnavailable: "The provider is temporarily unavailable — try again shortly.",
        ProviderBadRequest: "The request was rejected — the model name or input may be invalid.",
    }.get(type(exc), "")
    base = str(exc).strip()
    return f"{base} {hint}".strip()
