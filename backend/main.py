"""TabSage FastAPI application — API endpoints (Phase 6).

Stateless about secrets: holds no provider key. The user's key travels per
request in the `X-Provider-Key` header and is used transiently to build a
provider, then discarded. The session vector store is process-local + ephemeral.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import settings
from deps import get_provider_key
from providers import get_provider
from providers.base import (
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    ProviderUnavailable,
)
from rag import (
    EmbeddingModelMismatchError,
    EmptyContentError,
    PayloadTooLargeError,
    answer_question,
    describe_provider_error,
    embed_and_store,
    get_store,
    prepare_chunks,
)
from schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SessionResetRequest,
    SessionResetResponse,
)

app = FastAPI(
    title="TabSage API",
    version="0.1.0",
    description=(
        "Study-from-your-tabs RAG backend. BYOK: send your provider key in the "
        "`X-Provider-Key` header. The backend never stores or logs it."
    ),
)

# Restricted CORS — NEVER "*". Allowlist comes from settings (localhost in dev;
# the chrome-extension://<id> origin is added in Phase 7 once the id is known).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Provider-Key"],
)

# Process-wide, ephemeral vector store shared across requests.
store = get_store()


# ── error mapping ─────────────────────────────────────────────────────────
# Normalized provider errors → specific, friendly HTTP responses. Messages come
# from the provider layer and never contain key material.
_PROVIDER_STATUS: dict[type[ProviderError], int] = {
    ProviderAuthError: status.HTTP_401_UNAUTHORIZED,
    ProviderBadRequest: status.HTTP_400_BAD_REQUEST,
    ProviderRateLimit: status.HTTP_429_TOO_MANY_REQUESTS,
    ProviderTimeout: status.HTTP_504_GATEWAY_TIMEOUT,
    ProviderUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _provider_http_error(exc: ProviderError) -> HTTPException:
    code = _PROVIDER_STATUS.get(type(exc), status.HTTP_502_BAD_GATEWAY)
    return HTTPException(status_code=code, detail=describe_provider_error(exc))


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Convenience redirect: the bare root has no API; send users to the docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Deployment health check. No secrets."""
    return HealthResponse(status="ok")


# ── RAG endpoints ───────────────────────────────────────────────────────────
# Defined as sync `def` so FastAPI runs the blocking provider/store calls in a
# threadpool instead of stalling the event loop.

@app.post("/ingest", response_model=IngestResponse, tags=["rag"])
def ingest(
    body: IngestRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> IngestResponse:
    """Clean → chunk → embed → store one tab's text. Returns chunks indexed."""
    try:
        provider = get_provider(body.provider, provider_key)
    except ProviderError as exc:
        raise _provider_http_error(exc)

    # Volume cap: bound how many distinct tabs a session may hold. A refresh of
    # an already-stored tab (same tab_id) is allowed (it replaces via dedupe).
    existing_tabs = store.session_tab_ids(body.session_id)
    if (
        body.tab_id not in existing_tabs
        and len(existing_tabs) >= settings.max_sources_per_session
    ):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Session already holds the maximum of "
                f"{settings.max_sources_per_session} sources. Reset the session "
                f"or remove a tab before adding another."
            ),
        )

    try:
        chunks = prepare_chunks(
            body.text,
            session_id=body.session_id,
            tab_id=body.tab_id,
            title=body.title,
            url=body.url,
        )
    except PayloadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        )
    except EmptyContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )

    try:
        indexed = embed_and_store(store, provider, body.session_id, chunks)
    except EmbeddingModelMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ProviderError as exc:
        raise _provider_http_error(exc)

    return IngestResponse(
        session_id=body.session_id, tab_id=body.tab_id, chunks_indexed=indexed
    )


@app.post("/chat", response_model=ChatResponse, tags=["rag"])
def chat(
    body: ChatRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> ChatResponse:
    """Retrieve top-K chunks → grounded generate → answer + citations."""
    try:
        provider = get_provider(body.provider, provider_key)
    except ProviderError as exc:
        raise _provider_http_error(exc)

    try:
        result = answer_question(
            store,
            provider,
            body.session_id,
            body.question,
            source_tab_ids=body.source_tab_ids,
        )
    except EmbeddingModelMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ProviderError as exc:
        raise _provider_http_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )

    citations = [
        Citation(tab_id=c.tab_id, title=c.title, url=c.url, snippet=c.snippet)
        for c in result.citations
    ]
    return ChatResponse(
        answer=result.answer, citations=citations, grounded=result.grounded
    )


@app.post("/sessions/reset", response_model=SessionResetResponse, tags=["rag"])
def reset_session(body: SessionResetRequest) -> SessionResetResponse:
    """Delete a session's indexed content (also used when switching providers).

    No provider key needed — this only clears local session data.
    """
    removed = store.reset_session(body.session_id)
    return SessionResetResponse(session_id=body.session_id, chunks_removed=removed)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_dev,
    )
