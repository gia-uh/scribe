from __future__ import annotations

import io

from .._markitdown import converter
from ..result import ExtractResult

_FALLBACK_EXTS = {"html", "htm", "epub", "rtf", "odt", "odp", "ods", "xml", "json"}


def supports(ext: str) -> bool:
    return ext in _FALLBACK_EXTS


def convert(data: bytes, ext: str) -> ExtractResult:
    try:
        res = converter().convert_stream(io.BytesIO(data), file_extension="." + ext)
    except Exception as exc:
        raise ValueError(f"could not convert .{ext}: {exc}") from exc
    return ExtractResult(
        markdown=(res.text_content or "").strip(),
        title=(getattr(res, "title", None) or None),
        meta={"backend": "markitdown", "ext": ext},
    )


def convert_url(url: str) -> ExtractResult:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("from_url needs an http(s) URL")
    try:
        res = converter().convert(url)
    except Exception as exc:
        raise ValueError(f"could not fetch/convert {url!r}: {exc}") from exc
    return ExtractResult(
        markdown=(res.text_content or "").strip(),
        title=(getattr(res, "title", None) or None),
        meta={"backend": "markitdown", "url": url},
    )
