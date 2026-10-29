"""Shared pytest fixtures for the TabSage backend suite (Phase 11)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from rag import ChromaVectorStore

from ._fakes import FakeProvider, fake_factory


@pytest.fixture
def store() -> ChromaVectorStore:
    """A fresh, isolated in-memory Chroma store per test."""
    return ChromaVectorStore()


@pytest.fixture
def provider() -> FakeProvider:
    """A deterministic offline provider per test."""
    return FakeProvider()


@pytest.fixture
def session_id() -> str:
    """A unique session id so tests never collide in a shared store."""
    return f"sess-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """FastAPI TestClient with the provider factory replaced by the fake.

    Patches the name the endpoints call (`main.get_provider`) so no real key or
    network is involved. The app's module-level store singleton is reused; tests
    use unique session ids to stay isolated.
    """
    import main

    monkeypatch.setattr(main, "get_provider", fake_factory)
    return TestClient(main.app)
