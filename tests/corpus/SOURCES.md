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
- `two_column_spanning.pdf` — two columns plus a full-width caption crossing the
  gutter; guards the peak-valley column detector against a single spanning line.
- `watermark.pdf` — horizontal body text plus a rotated margin stamp; guards the
  `upright=True` filter that drops arXiv-style rotated watermarks.

These two were added after validating against real arXiv papers ("Attention Is
All You Need" — single-column; "Deep Residual Learning" — two-column), which
exposed word-gluing (fixed via `x_tolerance_ratio`), shallow real gutters (fixed
via peak-valley detection), and rotated-watermark noise (fixed via the upright
filter). The real PDFs are not committed (licensing); these generated fixtures
reproduce the same failure modes deterministically.

DOCX/PPTX/XLSX/CSV fixtures are built inline inside their test modules
(`python-docx` / `python-pptx` / `openpyxl` / stdlib `csv`), so there are no
binary fixtures to track for those formats.

## Tier 2 — real-world documents

Add only permissively-licensed (MIT / Apache-2.0 / CC-BY / public-domain) files
here, each with its source URL and license recorded below.

Apple iWork documents cannot be generated without a Mac, so these are vendored
from two upstream test corpora. Each has had its preview JPEGs and `thumbs/`
stripped (~2× smaller; no member any backend reads was touched).

From **Apache Tika** (`tika-parser-apple-module/src/test/resources/test-documents/`),
Apache License 2.0 — <https://github.com/apache/tika>:

- `iwork09.pages` ← `testPages.pages`. iWork '09 `index.xml`. Carries real
  `Title` / `Heading 1` / `Heading 2` paragraph styles, so it pins heading
  detection by style name.
- `iwork09.key` ← `testKeynote.key`. iWork '09 `index.apxl`; three slides, one
  with a speaker note.
- `iwork09.numbers` ← `testNumbers.numbers`. iWork '09 with two real tables. The
  Transactions table has a `col-span` cell in row 0 and a pop-up (`sf:pm`)
  column, which together pin grid alignment and selected-choice resolution; its
  running Balance column is arithmetic self-check for the whole grid.
- `iwork13.pages` ← `testPages2013.pages`. The `Index/*.iwa` generation.
- `iwork13.key` ← `testKeynote2018.key`. Saved as a **package** — the index is a
  nested `Presentation.key/Index.zip` — with 12 master slides carrying
  Indonesian placeholder copy, which is what the master-skipping test asserts is
  absent.
- `iwork_protected.pages` ← `testPagesPwdProtected.pages`. Password-protected;
  its members use Apple's own compression methods, which is how encryption is
  detected. Committed **verbatim** (it cannot be rewritten).

From **numbers-parser**, MIT — <https://github.com/masaccio/numbers-parser>:

- `iwork13.numbers` ← `tests/data/test-1.numbers`. Storage version 5 (what every
  Numbers since 2020 writes), two sheets, three tables, with two deliberately
  empty cells that pin cell placement.
