"""Normalized errors for the INGEST pipeline (Phase 3).

These let the endpoint layer (Phase 6) turn a failed ingest into a friendly,
specific HTTP response without knowing the internals of cleaning/chunking.
None of these messages ever contain the user's provider key or raw page text.
"""
from __future__ import annotations


class IngestError(Exception):
    """Base class for all ingest-pipeline errors."""


class EmptyContentError(IngestError):
    """The page had no usable text (empty, whitespace-only, or all boilerplate).

    Maps to HTTP 422 at the endpoint: the request was well-formed but there is
    nothing to index.
    """


class PayloadTooLargeError(IngestError):
    """A hard payload/volume cap was exceeded (Section 10 abuse limits).

    Raised when the raw page text is larger than ``max_text_chars`` or the
    cleaned text produces more than ``max_chunks`` chunks. Maps to HTTP 413.
    """
