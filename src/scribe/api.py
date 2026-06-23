from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import PurePath

from .result import ExtractResult


def _resolve_ext(filename: str | None, ext: str | None) -> str:
    if ext:
        return ext.lower().lstrip(".")
    if filename and "." in PurePath(filename).name:
        return PurePath(filename).name.rsplit(".", 1)[1].lower()
    return ""


def _backend_pdf(data: bytes) -> ExtractResult:
    from .backends import pdf

    return pdf.convert(data)


def _backend_docx(data: bytes) -> ExtractResult:
    from .backends import docx as docx_backend

    return docx_backend.convert(data)


def _backend_pptx(data: bytes) -> ExtractResult:
    from .backends import pptx as pptx_backend

    return pptx_backend.convert(data)


def _backend_xlsx(data: bytes) -> ExtractResult:
    from .backends import xlsx as xlsx_backend

    return xlsx_backend.convert(data)


def _backend_csv(data: bytes) -> ExtractResult:
    from .backends import csv as csv_backend

    return csv_backend.convert(data)


def _backend_text(data: bytes) -> ExtractResult:
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError:
        body = data.decode("latin-1")
    return ExtractResult(markdown=body, meta={"backend": "text"})


# Native backends. The long tail is handled by backends.fallback (see _dispatch).
_BACKENDS: dict[str, Callable[[bytes], ExtractResult]] = {
    "pdf": _backend_pdf,
    "docx": _backend_docx,
    "pptx": _backend_pptx,
    "xlsx": _backend_xlsx,
    "csv": _backend_csv,
    "txt": _backend_text,
    "md": _backend_text,
    "markdown": _backend_text,
}


def _dispatch(ext: str) -> Callable[[bytes], ExtractResult]:
    if ext in _BACKENDS:
        return _BACKENDS[ext]
    from .backends import fallback

    if fallback.supports(ext):
        return lambda data: fallback.convert(data, ext)
    raise ValueError(f"unsupported document type: {ext!r}")


def to_markdown(
    data: bytes, *, filename: str | None = None, ext: str | None = None
) -> ExtractResult:
    e = _resolve_ext(filename, ext)
    if not e:
        raise ValueError("cannot determine document type (pass filename or ext)")
    from .normalize import normalize_result

    return normalize_result(_dispatch(e)(data))


def from_path(path: str | os.PathLike) -> ExtractResult:
    with open(path, "rb") as fh:
        return to_markdown(fh.read(), filename=os.fspath(path))


def from_url(url: str) -> ExtractResult:
    from .backends import fallback
    from .normalize import normalize_result

    return normalize_result(fallback.convert_url(url))
