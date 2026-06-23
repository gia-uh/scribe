from pathlib import Path

import pytest

from scribe.backends.pdf import convert

C = Path(__file__).parent / "corpus"


def _md(name):
    return convert((C / name).read_bytes()).markdown


def test_two_column_not_interleaved():
    md = _md("two_column.pdf")
    assert md.index("COL1_H") < md.index("COL2_A")  # whole left col precedes right col


def test_table_becomes_markdown_table():
    md = _md("table.pdf")
    flat = md.replace(" ", "")
    assert "|Name|Qty|" in flat and "|Apple|3|" in flat


def test_headings_present():
    md = _md("headings.pdf")
    assert md.splitlines()[0].startswith("# ")
    assert "Document Title" in md.splitlines()[0]


def test_no_text_layer_returns_warning(tmp_path):
    from reportlab.pdfgen import canvas

    p = tmp_path / "blank.pdf"
    canvas.Canvas(str(p)).save()
    r = convert(p.read_bytes())
    assert r.markdown == ""
    assert any("no extractable text" in w for w in r.warnings)


def test_corrupt_pdf_raises():
    with pytest.raises(ValueError):
        convert(b"%PDF-1.4 not really a pdf")


def test_meta_reports_columns():
    r = convert((C / "two_column.pdf").read_bytes())
    assert r.meta["columns"] == 2
    assert r.meta["backend"] == "pdf"
