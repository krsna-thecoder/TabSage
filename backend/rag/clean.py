"""Page-text cleanup (Phase 3).

The extension sends `innerText` scraped from a study tab. That text carries a
lot of noise: navigation menus, repeated header/footer links, cookie banners,
inconsistent unicode whitespace, and long runs of blank lines. `clean_text`
normalizes this into compact, paragraph-preserving plain text so the chunker
produces meaningful, retrievable passages instead of chunks full of menu items.

Design choices (deliberately conservative — we never want to delete real study
content):
  * Unicode is NFKC-normalized so exotic spaces/quotes collapse to ASCII-ish
    forms; zero-width characters are stripped.
  * Whitespace within a line is collapsed to single spaces.
  * Blank lines are collapsed to at most one (paragraph break preserved).
  * Consecutive duplicate lines are dropped — the single most reliable signal
    of nav/menu boilerplate (site chrome tends to repeat identical link text)
    without guessing at site-specific patterns.
"""
from __future__ import annotations

import re
import unicodedata

# Zero-width / BOM-like characters that NFKC does not remove. Mapped to a space
# (then collapsed away) so they never glue tokens together or split words.
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_ZERO_WIDTH_TRANSLATE = {ord(c): " " for c in _ZERO_WIDTH}

# Runs of intra-line whitespace (spaces, tabs, form/vertical feeds) → one space.
_INLINE_WS = re.compile(r"[ \t\f\v]+")


def clean_text(raw: str) -> str:
    """Normalize raw page text into compact, paragraph-preserving plain text.

    Returns an empty string if there is nothing usable (empty input, or input
    that is only whitespace/boilerplate). Callers decide whether an empty
    result is an error (see `rag.ingest`).
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKC", raw)
    text = text.translate(_ZERO_WIDTH_TRANSLATE)
    # Normalize line endings so line handling is uniform across OSes/pages.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    out_lines: list[str] = []
    prev_line: str | None = None
    prev_blank = False

    for raw_line in text.split("\n"):
        line = _INLINE_WS.sub(" ", raw_line).strip()

        if not line:
            # Collapse consecutive blanks; never lead with a blank line.
            if out_lines and not prev_blank:
                out_lines.append("")
                prev_blank = True
            continue

        # Drop consecutive identical lines (repeated nav/menu/footer chrome).
        if line == prev_line:
            continue

        out_lines.append(line)
        prev_line = line
        prev_blank = False

    # Trim any trailing blank line left by the loop.
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines)
