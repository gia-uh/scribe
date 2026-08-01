# scribe

**The best MIT, no-LLM document → Markdown converter.**

`scribe` turns PDF, Word, PowerPoint, Excel, CSV (and the common long-tail
formats) into clean, structure-aware Markdown — deterministically, offline, and
free. **No LLM. No cloud. No GPU. MIT all the way down.**

It exists because the convenient options each fail one axis: `markitdown` reads
two-column PDFs straight across the page (interleaving the columns) and mangles
LaTeX/ligature text; `pymupdf4llm` is excellent but **AGPL** (a non-starter for
proprietary use); `docling`/`marker` need torch and multi-GB models. `scribe`
sits in the empty quadrant: **MIT + no-LLM + no-torch + genuinely good
structure.**

| Tool | License | LLM? | Two-column PDF | Notes |
|------|---------|------|----------------|-------|
| markitdown | MIT | no | ✗ (reads across) | thin wrappers, weak PDF |
| pymupdf4llm | **AGPL** | no | ✓ | great quality, license blocker |
| docling / marker | MIT/mixed | no (ML) | ✓ | torch + multi-GB models |
| **scribe** | **MIT** | **no** | **✓** | light, structure-aware |

## Install

```bash
# from the public repo (no PyPI release yet)
uv add "scribe-md @ git+https://github.com/gia-uh/scribe"
# or, for local development:
uv add --editable ../scribe
```

## Usage

```python
import scribe

result = scribe.from_path("paper.pdf")
print(result.markdown)
print(result.warnings)   # e.g. ["no extractable text layer"]
print(result.meta)       # {"backend": "pdf", "pages": 8, "columns": 2}

# from bytes (e.g. an upload)
result = scribe.to_markdown(data, filename="report.docx")

# from a URL
result = scribe.from_url("https://example.com/article")
```

### CLI

```bash
scribe report.pdf            # Markdown to stdout
scribe report.pdf -o out.md  # write to a file
```

## Format support

| Format | Backend | Quality |
|--------|---------|---------|
| PDF | `pdfplumber` + custom column/heading/table logic | first-class |
| DOCX | `python-docx` | first-class |
| PPTX | `python-pptx` (slides, bullets, tables, speaker notes) | first-class |
| XLSX | `openpyxl` (one table per sheet) | first-class |
| CSV | stdlib `csv` | first-class |
| **Pages / Keynote / Numbers** | own pure-Python iWork reader | first-class |
| TXT / MD | passthrough | first-class |
| HTML / EPUB / RTF / ODT / … | `markitdown` fallback | best-effort |

### Apple iWork (`.pages`, `.key`, `.numbers`)

Nothing else reads these: `markitdown` has no iWork backend, `kreuzberg` has an
open request for one, `keynote-parser` and `numbers-parser` each cover a single
app and need `python-snappy` (a C library) plus the `protobuf` runtime and
megabytes of generated Apple schema. `scribe` reads all three, in **pure Python,
with no new dependencies** — the Snappy variant and the protobuf wire walk are
about 70 lines between them.

Both document generations are supported: iWork '09's `index.xml`/`index.apxl`
and the `Index/*.iwa` format from iWork '13 onward (including the "saved as a
package" shape, where the real index is a nested `Index.zip`).

- **Pages** — body text in reading order, with headings from the paragraph
  style's name, falling back to font size relative to the document's body size
  so localised style names (`Título`, `Überschrift`) still produce headings.
- **Keynote** — one section per slide **in presentation order** (which the
  member filenames do not give you), slide titles, bullets, tables and speaker
  notes. Master slides are skipped, so the theme's placeholder copy stays out.
- **Numbers** — sheets and tables as Markdown tables, including dates, formula
  results and pop-up cells' selected values.

Password-protected documents raise with a message that says so. Where a table's
cells are in the 2013–2016 "pre-BNC" cell format, which is not decoded, the text
still converts and a warning names what was skipped — rather than guessing at
numbers.

Every backend's output passes through one **normalizer**: NFKC, ligature
expansion (`ﬁ→fi`), de-hyphenation of line-wraps, private-use-glyph stripping,
and whitespace cleanup — this is what fixes the garbled text LaTeX-produced PDFs
emit.

## Optional: AI-assisted enhancement (opt-in, not the default)

The **default path is 100% no-LLM** — that's scribe's identity and its safe
default. But for genuinely bad *scanned* PDFs (where the embedded OCR text is
full of character errors), there is an **opt-in** enhancer that uses a small
vision model to correct the OCR — in **grounded mode only**: it is given
scribe's deterministic text as an anchor plus the page image, and told to fix
character errors without inventing anything.

```bash
pip install "scribe-md[llm]"   # adds httpx + pypdfium2
```

```python
import scribe
result = scribe.enhance_pdf(pdf_bytes, api_key="sk-...")          # OpenRouter by default
# or point at any OpenAI-compatible endpoint (e.g. a local LM Studio):
result = scribe.enhance_pdf(pdf_bytes, api_key="x",
                            base_url="http://localhost:1234/v1/chat/completions",
                            model="...")
result.meta["enhanced"]   # True
result.warnings[0]        # "AI-assisted correction ... verify numbers/names ..."
```

Safeguards, because small VLMs hallucinate: **free image→Markdown transcription
is deliberately not offered** (ungrounded, a small model will confidently invent
legal text); each page's correction is **rejected and falls back to raw OCR** if
its length strays from the anchor; API/parse failures degrade gracefully per
page; and output is always tagged `enhanced=True` with a verify warning. **Even
so, numbers and proper names can still be misread — treat enhanced output as
AI-assisted, not authoritative.**

## Limitations (by design)

- **No LaTeX equation reconstruction.** Math-bearing text is made readable and
  correctly ordered, not turned back into `$...$` (that needs ML).
- **No OCR.** Scanned/image-only PDFs return an empty body with a
  `"no extractable text layer"` warning. (A flagged `tesseract` backend is a
  possible future addition — it is not an LLM.)
- DOCX tables currently render after the body text, not interleaved by document
  position.

## Licensing

MIT. Every runtime dependency is permissively licensed (MIT/BSD/Apache). There
is **no AGPL/GPL code anywhere** in the dependency tree — in particular, scribe
deliberately does **not** use PyMuPDF/`pymupdf4llm`.

Built by [GIA, Universidad de La Habana](https://github.com/gia-uh).
