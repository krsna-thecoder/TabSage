"""Unit tests for rag.clean.clean_text (Phase 3)."""
from __future__ import annotations

from rag import clean_text


def test_empty_and_whitespace_only_return_empty():
    assert clean_text("") == ""
    assert clean_text("   \n\n   \t  ") == ""


def test_collapses_inline_whitespace():
    assert clean_text("a     b\t\tc") == "a b c"


def test_collapses_blank_line_runs_to_single_break():
    out = clean_text("Para one.\n\n\n\n\nPara two.")
    assert out == "Para one.\n\nPara two."


def test_drops_consecutive_duplicate_lines():
    # Repeated nav/footer chrome collapses to one occurrence.
    raw = "Home\nHome\nHome\nReal content here.\nFooter\nFooter"
    out = clean_text(raw)
    assert out == "Home\nReal content here.\nFooter"


def test_strips_zero_width_and_bom_characters():
    raw = "hel\u200blo\ufeff world"
    # Zero-width chars become spaces, then collapse; words stay separable.
    assert clean_text(raw) == "hel lo world"


def test_nfkc_normalizes_exotic_whitespace():
    # Non-breaking space (U+00A0) normalizes and collapses to a plain space.
    assert clean_text("a\u00a0\u00a0b") == "a b"


def test_normalizes_crlf_line_endings():
    assert clean_text("line1\r\nline2\rline3") == "line1\nline2\nline3"


def test_no_leading_or_trailing_blank_lines():
    out = clean_text("\n\n  real  \n\n")
    assert out == "real"


def test_preserves_real_multiparagraph_content():
    raw = "Title\n\nFirst paragraph of study notes.\n\nSecond paragraph."
    out = clean_text(raw)
    assert out == "Title\n\nFirst paragraph of study notes.\n\nSecond paragraph."
