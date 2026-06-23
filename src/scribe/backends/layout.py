from __future__ import annotations

import re
import statistics

_BULLET = re.compile(r"^[•‣⁃●◦\-–\*]$")
_NUMBERED = re.compile(r"^(\d{1,2})[.)]$")


def group_lines(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    """Group words into visual lines by `top` proximity, each line sorted x0."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
    return lines


def _line_size(line: list[dict]) -> float:
    return statistics.median(w["size"] for w in line)


def _join_paragraph(lines: list[str]) -> str:
    """Join wrapped lines into a paragraph, merging hyphenated line-breaks
    (a line ending in letter+'-' fuses with the next without a space)."""
    s = ""
    for ln in lines:
        if not s:
            s = ln
        elif re.search(r"[A-Za-z]-$", s):
            s = s[:-1] + ln
        else:
            s = s + " " + ln
    return s


def words_to_markdown(column_words: list[dict]) -> str:
    """Turn a column's worth of words into Markdown: headings (by font size),
    bullet/numbered lists, and reflowed paragraphs."""
    if not column_words:
        return ""
    lines = group_lines(column_words)
    body = statistics.median([w["size"] for w in column_words]) or 10.0
    out: list[str] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(_join_paragraph(para))
            para.clear()

    for line in lines:
        text = " ".join(w["text"] for w in line).strip()
        if not text:
            continue
        first = line[0]["text"]
        size = _line_size(line)
        if _BULLET.match(first):
            flush()
            out.append("- " + " ".join(w["text"] for w in line[1:]).strip())
            continue
        m = _NUMBERED.match(first)
        if m:
            flush()
            out.append(f"{m.group(1)}. " + " ".join(w["text"] for w in line[1:]).strip())
            continue
        ratio = size / body
        if ratio >= 1.15 and len(text) <= 120:
            flush()
            level = 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3
            out.append("#" * level + " " + text)
            continue
        para.append(text)
    flush()
    return "\n\n".join(out)
