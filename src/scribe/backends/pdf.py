from __future__ import annotations

import io

import pdfplumber

from ..result import ExtractResult
from .columns import segment_columns
from .layout import words_to_markdown


def _table_to_md(tbl: list[list]) -> str:
    rows = [
        [("" if c is None else str(c)).strip().replace("\n", " ") for c in row]
        for row in tbl
        if row
    ]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, *body = rows
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def convert(data: bytes) -> ExtractResult:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"could not open PDF: {exc}") from exc

    parts: list[str] = []
    max_cols = 1
    n = 0
    try:
        with pdf:
            n = len(pdf.pages)
            for page in pdf.pages:
                tables = page.find_tables()
                table_bboxes = [t.bbox for t in tables]
                for t in tables:
                    md = _table_to_md(t.extract())
                    if md:
                        parts.append(md)
                words = page.extract_words(extra_attrs=["size", "fontname"])

                def _in_table(w: dict, bboxes=table_bboxes) -> bool:
                    cx = (w["x0"] + w["x1"]) / 2
                    cy = (w["top"] + w["bottom"]) / 2
                    return any(
                        x0 <= cx <= x1 and y0 <= cy <= y1 for (x0, y0, x1, y1) in bboxes
                    )

                words = [w for w in words if not _in_table(w)]
                cols = segment_columns(words, page.width, page.height)
                max_cols = max(max_cols, len(cols))
                for col in cols:
                    md = words_to_markdown(col)
                    if md.strip():
                        parts.append(md)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"could not parse PDF: {exc}") from exc

    markdown = "\n\n".join(p for p in parts if p.strip())
    warnings = [] if markdown.strip() else ["no extractable text layer (scanned image?)"]
    return ExtractResult(
        markdown=markdown,
        title=None,
        warnings=warnings,
        meta={"backend": "pdf", "pages": n, "columns": max_cols},
    )
