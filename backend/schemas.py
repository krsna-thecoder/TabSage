"""Pydantic models for the TabSage API request/response contract.

Note: the user's provider key is NEVER part of any body model. It travels only
in the `X-Provider-Key` header (see deps.py).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from config import settings


class Provider(str, Enum):
    """Supported model providers (BYOK)."""

    gemini = "gemini"  # default
    openai = "openai"  # optional


class HealthResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])


class IngestRequest(BaseModel):
    """Body for POST /ingest."""

    tab_id: str = Field(..., description="Stable id for the source tab.")
    title: str = Field(..., description="Page title, used in citations.")
    url: str = Field(..., description="Page URL, used in citations.")
    text: str = Field(
        ...,
        min_length=1,
        description="Extracted visible page text.",
    )
    session_id: str = Field(..., description="Extension-owned session id.")
    provider: Provider = Field(
        default=Provider.gemini,
        description="Which provider the user's key belongs to.",
    )


class IngestResponse(BaseModel):
    session_id: str
    tab_id: str
    chunks_indexed: int


class Citation(BaseModel):
    """A source reference backing an answer."""

    tab_id: str
    title: str
    url: str
    snippet: str | None = None


class ChatRequest(BaseModel):
    """Body for POST /chat."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=settings.max_question_chars,
        description="The user's study question.",
    )
    session_id: str = Field(..., description="Extension-owned session id.")
    source_tab_ids: list[str] | None = Field(
        default=None,
        description="Optional filter: restrict retrieval to these tabs.",
    )
    provider: Provider = Field(
        default=Provider.gemini,
        description="Which provider the user's key belongs to.",
    )


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    grounded: bool = Field(
        default=True,
        description=(
            "True when the answer came from the selected tabs; False for the "
            "honest 'not in your tabs' refusal (no citations)."
        ),
    )


class SessionResetRequest(BaseModel):
    """Body for POST /sessions/reset (also used when switching providers)."""

    session_id: str = Field(..., description="Session to clear.")


class SessionResetResponse(BaseModel):
    session_id: str
    chunks_removed: int
