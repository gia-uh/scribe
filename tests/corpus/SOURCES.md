# Test corpus provenance

## Tier 1 — generated fixtures (no license concerns)

All `*.pdf` here are generated deterministically by `tests/make_fixtures.py`
(reportlab) with sentinel tokens. Regenerate with:

    uv run python tests/make_fixtures.py

- `two_column.pdf` — two text columns; col 1 carries `COL1_A…COL1_H`, col 2
  carries `COL2_A…COL2_H`. Tests assert the whole left column precedes the
  right (no interleaving).
- `hyphenation.pdf` — a word split across a line break (`hyphen-` / `ation`).
- `table.pdf` — a 2×2 ruled grid (`Name/Qty`, `Apple/3`).
- `headings.pdf` — a large-font title over body paragraphs.

DOCX/PPTX/XLSX/CSV fixtures are built inline inside their test modules
(`python-docx` / `python-pptx` / `openpyxl` / stdlib `csv`), so there are no
binary fixtures to track for those formats.

## Tier 2 — real-world documents

Add only CC-BY or public-domain files here, each with its source URL and
license recorded below. (None committed yet.)
