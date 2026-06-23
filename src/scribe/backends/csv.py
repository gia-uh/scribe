from __future__ import annotations

import csv as _csv
import io

from ..result import ExtractResult


def convert(data: bytes) -> ExtractResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    rows = list(_csv.reader(io.StringIO(text)))
    if not rows:
        return ExtractResult(markdown="", meta={"backend": "csv"})
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, *body = rows
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return ExtractResult(markdown="\n".join(out), meta={"backend": "csv"})
