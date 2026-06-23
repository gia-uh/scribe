import pytest

from scribe.api import _resolve_ext, to_markdown


def test_resolve_ext_from_filename():
    assert _resolve_ext("Report.PDF", None) == "pdf"
    assert _resolve_ext("a.b.docx", None) == "docx"
    assert _resolve_ext("noext", None) == ""


def test_resolve_ext_explicit_wins():
    assert _resolve_ext("x.pdf", "docx") == "docx"


def test_unsupported_ext_raises():
    with pytest.raises(ValueError):
        to_markdown(b"data", ext="xyz")


def test_missing_type_raises():
    with pytest.raises(ValueError):
        to_markdown(b"data")
