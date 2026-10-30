"""TabSage FastAPI application — API endpoints + production hardening.

Stateless about secrets: holds no provider key. The user's key travels per
request in the `X-Provider-Key` header and is used transiently to build a
provider, then discarded. The session vector store is process-local + ephemeral.

Phase 9 adds the production surface around those endpoints:
  * a background job that sweeps idle sessions out of the ephemeral store;
  * per-client / per-session rate limiting (ratelimit.py);
  * access logging that records method/path/status/latency only — never the
    request headers or bodies, which carry the key and raw page text.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

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
from ratelimit import enforce_client_rate_limit, enforce_ingest_quota
from rag import (
    EmbeddingModelMismatchError,
    EmptyContentError,
    PayloadTooLargeError,
    answer_question,
    answer_question_stream,
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


# ── logging ───────────────────────────────────────────────────────────────
# A dedicated logger so TabSage lines are distinguishable from uvicorn's. It is
# wired NEVER to touch headers or bodies (see `log_requests` below).
logger = logging.getLogger("tabsage")


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s tabsage %(message)s")
        )
        logger.addHandler(handler)
        logger.propagate = False


_configure_logging()

# Process-wide, ephemeral vector store shared across requests.
store = get_store()


# ── lifespan: background idle-session sweeper ─────────────────────────────────
async def _purge_loop() -> None:
    """Periodically drop sessions idle longer than the TTL (auto-expiry job).

    Keeps the ephemeral in-memory store bounded without persisting anything.
    Runs on `settings.purge_interval_seconds`; errors are logged and the loop
    continues so one bad cycle can't kill the sweeper.
    """
    while True:
        try:
            await asyncio.sleep(settings.purge_interval_seconds)
            purged = await asyncio.to_thread(store.purge_expired)
            if purged:
                logger.info("Purged %d idle session(s).", len(purged))
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 - never let the sweeper die silently
            logger.exception("Session purge cycle failed; continuing.")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TabSage API starting (env=%s).", settings.env)
    # Surface the resolved CORS allowlist — the most common post-deploy gotcha
    # (the extension's chrome-extension://<id> origin must be present). Safe to
    # log: origins are not secrets.
    logger.info("CORS allowed origins: %s", settings.allowed_origins_list)
    task = asyncio.create_task(_purge_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("TabSage API shutting down.")


app = FastAPI(
    title="TabSage API",
    version="0.1.0",
    description=(
        "Study-from-your-tabs RAG backend. BYOK: send your provider key in the "
        "`X-Provider-Key` header. The backend never stores or logs it."
    ),
    lifespan=lifespan,
)

# Restricted CORS — NEVER "*". Allowlist comes from settings (localhost in dev;
# the chrome-extension://<id> origin is added in Phase 7 once the id is known).
# Added FIRST so it sits inside the access-log middleware and still attaches
# CORS headers to error responses (e.g. a 429), which the extension must read.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Provider-Key", "X-Client-Token"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Structured access log — method, path, status, latency only.

    Deliberately reads NOTHING from headers or the body: the provider key lives
    in `X-Provider-Key` and raw page text in the JSON body, and neither may ever
    be logged (Section 10). The peer IP is included for abuse monitoring.
    """
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    client = request.client.host if request.client else "-"
    logger.info(
        "%s %s -> %d (%.1f ms) client=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        client,
    )
    return response


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

@app.post(
    "/ingest",
    response_model=IngestResponse,
    tags=["rag"],
    dependencies=[Depends(enforce_client_rate_limit)],
)
def ingest(
    body: IngestRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> IngestResponse:
    """Clean → chunk → embed → store one tab's text. Returns chunks indexed."""
    # Per-session ingest cap: bound how fast one session writes to the store
    # (the main storage/compute cost surface), on top of the per-client limit.
    enforce_ingest_quota(body.session_id)

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


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["rag"],
    dependencies=[Depends(enforce_client_rate_limit)],
)
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


def _sse(obj: dict) -> str:
    """Encode one Server-Sent Event line."""
    return f"data: {json.dumps(obj)}\n\n"


@app.post(
    "/chat/stream",
    tags=["rag"],
    dependencies=[Depends(enforce_client_rate_limit)],
)
def chat_stream(
    body: ChatRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> StreamingResponse:
    """Streaming /chat: emits SSE `delta` events as the answer is produced, then
    a final `done` event with citations + the grounded flag.

    Because the HTTP 200 + headers are sent before generation runs, errors that
    occur mid-stream are delivered as an `error` event (with the status code the
    non-streaming endpoint would have returned) rather than an HTTP error.
    """
    try:
        provider = get_provider(body.provider, provider_key)
    except ProviderError as exc:
        raise _provider_http_error(exc)

    def event_gen():
        try:
            for kind, payload in answer_question_stream(
                store,
                provider,
                body.session_id,
                body.question,
                source_tab_ids=body.source_tab_ids,
            ):
                if kind == "delta":
                    yield _sse({"type": "delta", "text": payload})
                else:  # ("done", ChatResult)
                    result = payload
                    citations = [
                        {
                            "tab_id": c.tab_id,
                            "title": c.title,
                            "url": c.url,
                            "snippet": c.snippet,
                        }
                        for c in result.citations
                    ]
                    yield _sse(
                        {
                            "type": "done",
                            "citations": citations,
                            "grounded": result.grounded,
                        }
                    )
        except EmbeddingModelMismatchError as exc:
            yield _sse({"type": "error", "status": 409, "detail": str(exc)})
        except ProviderError as exc:
            yield _sse(
                {
                    "type": "error",
                    "status": _PROVIDER_STATUS.get(type(exc), status.HTTP_502_BAD_GATEWAY),
                    "detail": describe_provider_error(exc),
                }
            )
        except ValueError as exc:
            yield _sse({"type": "error", "status": 422, "detail": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/sessions/reset",
    response_model=SessionResetResponse,
    tags=["rag"],
    dependencies=[Depends(enforce_client_rate_limit)],
)
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
