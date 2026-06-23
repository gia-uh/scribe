from __future__ import annotations

import re
import unicodedata

from .result import ExtractResult

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}
# Private Use Area: BMP (E000-F8FF) + planes 15/16 — unrecoverable glyphs.
_PUA = re.compile(r"[-\U000f0000-\U0010fffd]")
_DEHYPHEN = re.compile(r"(\w)-\n(\w)")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANKS = re.compile(r"\n{3,}")
# Control chars except \n (\x0a) and \t (\x09).
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_text(s: str) -> tuple[str, list[str]]:
    """Clean extracted text: expand ligatures, NFKC-normalize, strip private-use
    and control glyphs, de-hyphenate line-wraps, and collapse whitespace.
    Returns (cleaned_text, warnings)."""
    warnings: list[str] = []
    for lig, repl in _LIGATURES.items():
        s = s.replace(lig, repl)
    s = unicodedata.normalize("NFKC", s)
    pua = _PUA.findall(s)
    if pua:
        s = _PUA.sub("", s)
        warnings.append(f"{len(pua)} private-use glyph(s) dropped")
    s = _CTRL.sub("", s)
    s = s.replace(" ", " ")  # NBSP → space
    s = _DEHYPHEN.sub(r"\1\2", s)
    s = _TRAILING_WS.sub("", s)
    s = _BLANKS.sub("\n\n", s)
    return s.strip() + "\n", warnings


def normalize_result(r: ExtractResult) -> ExtractResult:
    md, warns = normalize_text(r.markdown)
    r.markdown = md
    r.warnings.extend(warns)
    return r
