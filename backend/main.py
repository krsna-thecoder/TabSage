"""TabSage FastAPI application — backend foundations (Phase 1).

Stateless about secrets: holds no provider key. The user's key travels per
request in the `X-Provider-Key` header and is used transiently.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from deps import get_provider_key
from schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
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


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Deployment health check. No secrets."""
    return HealthResponse(status="ok")


# ── Phase 6 endpoints (stubs) ─────────────────────────────────────────────
# Wired here so the request/response models and the X-Provider-Key dependency
# are exercisable in Swagger now. RAG logic is implemented in Phases 3–6.

@app.post("/ingest", response_model=IngestResponse, tags=["rag"])
async def ingest(
    body: IngestRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> IngestResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ingest is implemented in Phase 6 (clean → chunk → embed → store).",
    )


@app.post("/chat", response_model=ChatResponse, tags=["rag"])
async def chat(
    body: ChatRequest,
    provider_key: Annotated[str, Depends(get_provider_key)],
) -> ChatResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chat is implemented in Phase 6 (retrieve → generate → cite).",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_dev,
    )
