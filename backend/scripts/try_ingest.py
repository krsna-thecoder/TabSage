"""Manual Phase 3 check — clean + chunk (no network, no key needed).

Usage (from the backend/ folder, venv active):
    python scripts/try_ingest.py

It runs a noisy sample page through clean_text + chunk_text, prints the
before/after and the resulting chunks with metadata, then exercises the edge
cases (empty, tiny, huge) and the payload caps so you can eyeball that
everything behaves.
"""
from __future__ import annotations

import os
import sys

# Make the backend package root importable when run as a script.
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from rag import (  # noqa: E402
    EmptyContentError,
    PayloadTooLargeError,
    chunk_text,
    clean_text,
    prepare_chunks,
)

# A deliberately messy "page": repeated nav lines, zero-width chars, weird
# unicode spaces, and big blank-line gaps around the real study content.
SAMPLE = (
    "Home\nHome\nHome\n"
    "Skip to content\u200b\n\n\n"
    "\u00a0\u00a0Menu   |   Login   |   Sign up\n\n"
    "Binary Search\n\n"
    "Binary search is an efficient algorithm for finding an item from a sorted "
    "list of items. It works by repeatedly dividing in half the portion of the "
    "list that could contain the item, until you've narrowed the possibilities "
    "to just one.\n\n"
    "The time complexity of binary search is O(log n), which is far better than "
    "the O(n) of a linear scan over the same sorted array.\n\n"
    "Footer\nFooter\n\u00a0\n"
)

META = dict(
    session_id="sess-demo",
    tab_id="tab-42",
    title="Binary Search — Notes",
    url="https://example.com/binary-search",
)


def _rule(label: str) -> None:
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


def main() -> int:
    _rule("1) clean_text — raw vs cleaned")
    print(f"raw length:     {len(SAMPLE)} chars")
    cleaned = clean_text(SAMPLE)
    print(f"cleaned length: {len(cleaned)} chars")
    print("\n--- cleaned text ---")
    print(cleaned)

    _rule("2) prepare_chunks — clean + chunk + limits (small chunks to show splits)")
    chunks = prepare_chunks(SAMPLE, chunk_size=200, chunk_overlap=40, **META)
    print(f"produced {len(chunks)} chunk(s)\n")
    for c in chunks:
        print(f"[chunk {c.metadata['chunk_index']}] len={len(c.text)} "
              f"tab={c.metadata['tab_id']} title={c.metadata['title']!r}")
        print(f"    {c.text!r}\n")

    _rule("3) edge case — empty / whitespace-only page")
    print("clean_text(''):        ", repr(clean_text("")))
    print("clean_text('   \\n\\n'):", repr(clean_text("   \n\n")))
    try:
        prepare_chunks("   \n\n   ", **META)
        print("ERROR: expected EmptyContentError")
    except EmptyContentError as e:
        print("EmptyContentError raised as expected ->", e)

    _rule("4) edge case — tiny page (single chunk)")
    tiny = prepare_chunks("Just one short line.", **META)
    print(f"tiny page -> {len(tiny)} chunk(s):", repr(tiny[0].text))

    _rule("5) edge case — huge page exceeds max_text_chars")
    huge = "word " * 100_000  # ~500k chars, over the 200k default cap
    try:
        prepare_chunks(huge, max_text_chars=200_000, **META)
        print("ERROR: expected PayloadTooLargeError (text size)")
    except PayloadTooLargeError as e:
        print("PayloadTooLargeError raised as expected ->", e)

    _rule("6) edge case — too many chunks exceeds max_chunks")
    many = ("Sentence number about algorithms and data structures. " * 400)
    try:
        prepare_chunks(many, chunk_size=100, chunk_overlap=10, max_chunks=5, **META)
        print("ERROR: expected PayloadTooLargeError (chunk count)")
    except PayloadTooLargeError as e:
        print("PayloadTooLargeError raised as expected ->", e)

    print("\nOK — clean + chunk pipeline behaves as expected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
