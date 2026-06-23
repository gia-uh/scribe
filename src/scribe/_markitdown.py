from __future__ import annotations

_md = None


def converter():
    global _md
    if _md is None:
        from markitdown import MarkItDown

        _md = MarkItDown()
    return _md
