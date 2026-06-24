# AGENTS.md — scribe

You're an AI agent picking up **scribe**. This file is the door.

## What it is

An MIT-licensed, **no-LLM** document → Markdown converter: PDF, DOCX, PPTX,
XLSX, CSV (first-class native backends) + a markitdown fallback for the long
tail (HTML/EPUB/RTF/ODT/…). Public OSS under `github.com/gia-uh/scribe`; PyPI
dist `scribe-md`, import `scribe`. First consumers: magpie + superbot (AInBox).

Design + plan live in the workspace vault (not this repo):
- Spec: `vault/Atlas/Architecture/2026-06-23-scribe-document-extraction-design.md`
- Plan: `vault/Atlas/Architecture/plans/2026-06-23-scribe-document-extraction-plan.md`

## Hard rules

- **MIT only.** Every runtime dep must be MIT/BSD/Apache. **Never** PyMuPDF/
  `pymupdf4llm` (AGPL). CI/`tests` guard this — keep it true.
- **No LLM, no torch, no ML models** in the default conversion path. Ever.
  The *only* LLM touchpoint is `scribe.enhance_pdf` (`src/scribe/enhance.py`) —
  opt-in, behind the `[llm]` extra, never imported by the core, grounded-
  correction mode only (never free transcription). Findings that justify the
  design: `vault/+/agent_drafts/design_docs/2026-06-23-scribe-optional-vlm-hypotheses.md`.
- Python 3.12, `uv` for everything (`uv run …`), never `pip install`.

## Layout

```
src/scribe/
├── api.py          dispatch by extension → backend → normalize → ExtractResult
├── result.py       ExtractResult(markdown, title, warnings, meta)
├── normalize.py    PURE: NFKC, ligatures, de-hyphenation, PUA strip, whitespace
├── cli.py          `scribe <file> [-o out.md]`
├── enhance.py      OPT-IN VLM grounded correction for scans ([llm] extra only)
├── _markitdown.py  lazy MarkItDown singleton (fallback only)
└── backends/
    ├── pdf.py      pdfplumber + columns + layout + tables
    ├── columns.py  PURE: vertical-gutter column segmentation
    ├── layout.py   PURE: heading/list inference, paragraph reflow, de-hyphenation
    ├── docx.py / pptx.py / xlsx.py / csv.py   native backends
    └── fallback.py markitdown wrapper for the long tail
```

The three PURE modules (`normalize`, `columns`, `layout`) hold the tricky logic
and are unit-tested in isolation — touch them with tests first.

## Tests

`uv run pytest -q` (fast, ~1s). PDF fixtures are generated deterministically:
`uv run python tests/make_fixtures.py` (committed; don't regenerate casually).
DOCX/PPTX/XLSX/CSV fixtures are built inline in their test modules.

Known soft spots to retune with tests, not by feel: column-gutter thresholds
in `columns.py`, heading font-size ratios in `layout.py`.

## Conventions

- Ships to `main` (no PR cycle).
- Conventional commits, one logical change each.
- `uv run ruff check .` must pass.
