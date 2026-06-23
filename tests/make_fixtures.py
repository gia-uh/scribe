"""Generate deterministic PDF fixtures with sentinel tokens. Run once:

    uv run python tests/make_fixtures.py

Commit the resulting PDFs; tests do not regenerate them."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "corpus"


def two_column():
    c = canvas.Canvas(str(OUT / "two_column.pdf"), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica", 11)
    for i in range(8):
        tok = f"COL1_{chr(65 + i)}"
        c.drawString(60, h - 100 - i * 20, f"{tok} left column body text here")
    for i in range(8):
        tok = f"COL2_{chr(65 + i)}"
        c.drawString(w / 2 + 30, h - 100 - i * 20, f"{tok} right column body text here")
    c.save()


def hyphenation():
    c = canvas.Canvas(str(OUT / "hyphenation.pdf"), pagesize=A4)
    c.setFont("Helvetica", 11)
    c.drawString(60, 740, "hyphen-")
    c.drawString(60, 726, "ation works across lines")
    c.save()


def table():
    c = canvas.Canvas(str(OUT / "table.pdf"), pagesize=A4)
    c.setFont("Helvetica", 11)
    xs, ys = [60, 200, 340], [740, 712, 684]
    for y in ys:
        c.line(xs[0], y, xs[-1], y)
    for x in xs:
        c.line(x, ys[0], x, ys[-1])
    cells = [["Name", "Qty"], ["Apple", "3"]]
    for r, row in enumerate(cells):
        for col, val in enumerate(row):
            c.drawString(xs[col] + 5, ys[r] - 18, val)
    c.save()


def headings():
    c = canvas.Canvas(str(OUT / "headings.pdf"), pagesize=A4)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(60, 760, "Document Title")
    c.setFont("Helvetica", 11)
    for i in range(4):
        c.drawString(60, 720 - i * 16, f"Body paragraph line {i} with content.")
    c.save()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    two_column()
    hyphenation()
    table()
    headings()
    print("fixtures written to", OUT)
