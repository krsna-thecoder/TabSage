"""Vector store: interface + ephemeral Chroma implementation (Phase 4).

Design (see DOCUMENTATION Sections 6, 7, 9):

* **Behind an interface.** Everything downstream (Phase 5 chat) depends only on
  `VectorStore`, so swapping Chroma for pgvector later is a config choice.

* **Ephemeral by default.** The dev/default impl uses Chroma's in-memory
  `EphemeralClient` — nothing is written to disk, so scraped page content is
  not persisted server-side (less cost, less privacy risk). A short TTL bounds
  memory during a run; `purge_expired()` drops idle sessions. (A background
  scheduler that calls it is wired in Phase 9; persistence is an opt-in later.)

* **Session isolation via one collection per session.** Each `session_id` maps
  to its own Chroma collection. This gives clean isolation, makes reset a
  single `delete_collection`, and — importantly — avoids a vector-dimension
  clash: Gemini embeddings are 3072-dim and OpenAI's are 1536-dim, and a Chroma
  collection has a fixed dimension once its first vector lands.

* **Embedding-model consistency guard.** Every chunk records the
  `embedding_model_id` that produced it. A session is built with exactly one
  model; adding or querying with a different model raises
  `EmbeddingModelMismatchError` instead of returning meaningless similarity
  results. The caller (Phase 5/6) turns that into a refuse-or-auto-reset.

* **Dedupe.** Re-ingesting a tab replaces that tab's chunks (delete-by-tab_id
  then add), so refreshing a page never double-counts it.
"""
from __future__ import annotations

import hashlib
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import chromadb

from config import settings

from .chunker import Chunk

# Default number of chunks to retrieve per query (tunable in Phase 11).
DEFAULT_TOP_K = 5

# Chroma collections use cosine space; TabSage supplies its own embeddings, so
# no Chroma embedding function is ever configured or invoked.
_COSINE = {"hnsw": {"space": "cosine"}}


class StoreError(Exception):
    """Base class for vector-store errors."""


class EmbeddingModelMismatchError(StoreError):
    """A session's stored embedding model differs from the one now in use.

    Embeddings from different models are not comparable, so the session must be
    reset before it can be (re)built or queried with the new model. Carries the
    two model ids so the caller can explain / auto-reset.
    """

    def __init__(self, session_id: str, stored: str, requested: str) -> None:
        self.session_id = session_id
        self.stored = stored
        self.requested = requested
        super().__init__(
            f"Session {session_id!r} was built with embedding model {stored!r}, "
            f"but the request uses {requested!r}. Reset the session before "
            f"switching providers/models."
        )


@dataclass(frozen=True)
class Retrieved:
    """One retrieved chunk: its text, source metadata, and similarity score."""

    text: str
    metadata: dict[str, Any]
    # Cosine similarity in [-1, 1]; higher = more relevant (1.0 = identical).
    score: float


def _collection_name(session_id: str) -> str:
    """Map an arbitrary session id to a valid Chroma collection name.

    Chroma requires 3–512 chars from [a-zA-Z0-9._-], starting/ending
    alphanumeric. Hashing the session id guarantees a valid, stable name and
    keeps the raw id out of the backing store's naming.
    """
    digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:40]
    return f"tabsage-{digest}"


class VectorStore(ABC):
    """Interface for session-scoped vector storage + retrieval."""

    @abstractmethod
    def add(
        self,
        session_id: str,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        embedding_model_id: str,
    ) -> int:
        """Store `chunks` with their `embeddings`. Returns the number added.

        Replaces any existing chunks for the same tab_id(s) (dedupe). Raises
        `EmbeddingModelMismatchError` if the session already holds a different
        embedding model.
        """

    @abstractmethod
    def query(
        self,
        session_id: str,
        query_embedding: Sequence[float],
        embedding_model_id: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        source_tab_ids: Sequence[str] | None = None,
    ) -> list[Retrieved]:
        """Return the top-K most similar chunks for the session.

        Optionally restricts retrieval to `source_tab_ids`. Raises
        `EmbeddingModelMismatchError` on a model mismatch; returns [] if the
        session has nothing stored.
        """

    @abstractmethod
    def reset_session(self, session_id: str) -> int:
        """Delete all of a session's content. Returns chunks removed."""

    @abstractmethod
    def delete_tab(self, session_id: str, tab_id: str) -> int:
        """Delete one tab's chunks from a session. Returns chunks removed."""

    @abstractmethod
    def session_embedding_model(self, session_id: str) -> str | None:
        """The embedding-model id a session was built with, or None if empty."""

    @abstractmethod
    def session_tab_ids(self, session_id: str) -> list[str]:
        """Distinct tab_ids currently stored for a session."""

    @abstractmethod
    def count(self, session_id: str) -> int:
        """Number of chunks stored for a session."""

    @abstractmethod
    def purge_expired(self, ttl_seconds: int | None = None) -> list[str]:
        """Drop sessions idle longer than the TTL. Returns purged session ids."""


class ChromaVectorStore(VectorStore):
    """Ephemeral, in-memory Chroma store (dev/default).

    Thread-safe for the small amount of shared bookkeeping (the per-session
    last-seen registry). Chroma client calls are themselves safe to interleave.
    """

    def __init__(self) -> None:
        self._client = chromadb.EphemeralClient()
        # session_id -> last access time (monotonic). Doubles as the existence
        # registry, so reads never create empty collections.
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    # ── internal helpers ────────────────────────────────────────────────
    def _collection(self, session_id: str):
        return self._client.get_or_create_collection(
            name=_collection_name(session_id), configuration=_COSINE
        )

    def _exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._last_seen

    def _touch(self, session_id: str) -> None:
        with self._lock:
            self._last_seen[session_id] = time.monotonic()

    def _forget(self, session_id: str) -> None:
        with self._lock:
            self._last_seen.pop(session_id, None)

    # ── interface ───────────────────────────────────────────────────────
    def add(
        self,
        session_id: str,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        embedding_model_id: str,
    ) -> int:
        if len(chunks) != len(embeddings):
            raise StoreError(
                f"chunks/embeddings length mismatch: {len(chunks)} vs {len(embeddings)}."
            )
        if not chunks:
            return 0

        stored_model = self.session_embedding_model(session_id)
        if stored_model is not None and stored_model != embedding_model_id:
            raise EmbeddingModelMismatchError(
                session_id, stored_model, embedding_model_id
            )

        col = self._collection(session_id)

        # Dedupe: replace any existing chunks for the tab_ids in this batch.
        for tab_id in {str(c.metadata["tab_id"]) for c in chunks}:
            col.delete(where={"tab_id": tab_id})

        ids: list[str] = []
        embs: list[list[float]] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        for chunk, emb in zip(chunks, embeddings):
            meta = dict(chunk.metadata)
            meta["embedding_model_id"] = embedding_model_id
            ids.append(f"{session_id}:{meta['tab_id']}:{meta['chunk_index']}")
            embs.append(list(emb))
            docs.append(chunk.text)
            metas.append(meta)

        col.add(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        self._touch(session_id)
        return len(ids)

    def query(
        self,
        session_id: str,
        query_embedding: Sequence[float],
        embedding_model_id: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        source_tab_ids: Sequence[str] | None = None,
    ) -> list[Retrieved]:
        if not self._exists(session_id):
            return []

        stored_model = self.session_embedding_model(session_id)
        if stored_model is None:
            return []
        if stored_model != embedding_model_id:
            raise EmbeddingModelMismatchError(
                session_id, stored_model, embedding_model_id
            )

        col = self._collection(session_id)
        where = None
        if source_tab_ids:
            where = {"tab_id": {"$in": list(source_tab_ids)}}

        kwargs: dict[str, Any] = {
            "query_embeddings": [list(query_embedding)],
            "n_results": max(1, top_k),
        }
        if where is not None:
            kwargs["where"] = where
        res = col.query(**kwargs)
        self._touch(session_id)

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: list[Retrieved] = []
        for doc, meta, dist in zip(docs, metas, dists):
            # Chroma cosine "distance" = 1 - cosine_similarity → recover score.
            out.append(Retrieved(text=doc, metadata=dict(meta), score=1.0 - dist))
        return out

    def reset_session(self, session_id: str) -> int:
        removed = self.count(session_id)
        try:
            self._client.delete_collection(name=_collection_name(session_id))
        except Exception:  # noqa: BLE001 - collection may not exist; that's fine
            pass
        self._forget(session_id)
        return removed

    def delete_tab(self, session_id: str, tab_id: str) -> int:
        if not self._exists(session_id):
            return 0
        col = self._collection(session_id)
        before = col.count()
        col.delete(where={"tab_id": tab_id})
        after = col.count()
        return before - after

    def session_embedding_model(self, session_id: str) -> str | None:
        if not self._exists(session_id):
            return None
        got = self._collection(session_id).get(limit=1, include=["metadatas"])
        metas = got.get("metadatas") or []
        if not metas:
            return None
        return metas[0].get("embedding_model_id")

    def session_tab_ids(self, session_id: str) -> list[str]:
        if not self._exists(session_id):
            return []
        got = self._collection(session_id).get(include=["metadatas"])
        seen: list[str] = []
        for meta in got.get("metadatas") or []:
            tab_id = meta.get("tab_id")
            if tab_id is not None and tab_id not in seen:
                seen.append(tab_id)
        return seen

    def count(self, session_id: str) -> int:
        if not self._exists(session_id):
            return 0
        return self._collection(session_id).count()

    def purge_expired(self, ttl_seconds: int | None = None) -> list[str]:
        ttl = settings.session_ttl_seconds if ttl_seconds is None else ttl_seconds
        now = time.monotonic()
        with self._lock:
            expired = [
                sid for sid, seen in self._last_seen.items() if now - seen > ttl
            ]
        for sid in expired:
            self.reset_session(sid)
        return expired


# ── process-wide singleton ──────────────────────────────────────────────
_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store() -> VectorStore:
    """Return the shared default vector store (ephemeral Chroma)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ChromaVectorStore()
    return _store
