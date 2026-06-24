"""Regression for a genuinely bad scan: a 1996 two-column Gaceta Oficial de Cuba
with a coat-of-arms cover, a multi-cell masthead, tiny OCR'd type, and heavy
scanner-speck noise. We cannot fix the OCR engine's character errors (that needs
OCR/AI, out of scope) — but the layout must be recovered and the speck noise
(dot leaders, stray punctuation) must be filtered out deterministically."""

from pathlib import Path

from scribe.backends.pdf import convert

UGLY = Path(__file__).parent / "corpus" / "ugly.pdf"


def _md():
    return convert(UGLY.read_bytes())


def test_two_column_body_detected():
    assert convert(UGLY.read_bytes()).meta["columns"] == 2


def test_body_text_recovered():
    md = _md().markdown
    # Title + body survive the noise filtering (OCR spelling may vary, these are stable).
    assert "REAFIRMACION" in md
    assert "ARTICULO" in md
    assert "1996" in md


def test_no_scanner_speck_lines_survive():
    md = _md().markdown
    speck = [
        s
        for ln in md.splitlines()
        if (s := ln.strip())
        and not any(c.isalpha() for c in s)  # no letters at all
        and (set(s) - set("#|-: "))  # and not a markdown structural line
    ]
    assert not speck, f"scanner-speck noise lines survived: {speck[:5]}"
