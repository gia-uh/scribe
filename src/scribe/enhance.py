"""OPTIONAL, opt-in VLM enhancement for scanned PDFs.

scribe's core is strictly no-LLM. This module is the *only* place an LLM is ever
involved, it is never on the default path, and it runs the model in
**grounded-correction mode only**: the deterministic OCR text is the anchor and
the page image is the reference, with a strict no-invention prompt. Free
image→Markdown transcription is deliberately NOT offered — small VLMs hallucinate
legal/official text catastrophically when ungrounded.

Even grounded, the model can still misread ambiguous tokens (numbers, names), so
output is tagged ``meta["enhanced"]=True`` and carries a verify warning. Treat it
as AI-assisted, not authoritative.

Requires the optional extra:  ``pip install "scribe-md[llm]"``  (httpx + pypdfium2).
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable

from .backends.pdf import page_to_markdown
from .result import ExtractResult

DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"  # fast, cheap, vision; NOT a reasoning model
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

_VERIFY_WARNING = (
    "AI-assisted correction (grounded VLM): verify numbers, dates, and proper "
    "names against the source — these can still be misread."
)

GROUNDED_PROMPT = (
    "Below is OCR text extracted from the attached scanned page, plus the page "
    "image. The OCR has character errors. Using the IMAGE as ground truth, output "
    "a corrected version of the SAME text.\n"
    "STRICT RULES:\n"
    "- Fix only clear OCR character errors (e.g. 'almno'->'alguno').\n"
    "- Do NOT add, remove, reorder, summarize, paraphrase, or 'improve' content.\n"
    "- Every sentence in your output must correspond to text visible in the image.\n"
    "- If unsure about a token, keep the OCR version unchanged.\n"
    "- Output ONLY the corrected text, no commentary.\n\n"
    "OCR TEXT:\n"
)

# Reject a correction whose length strays this far from the anchor — a strong
# signal the model went off-rails (truncated, or free-wrote new content).
_MIN_RATIO, _MAX_RATIO = 0.5, 1.8


def _build_payload(text: str, image_png: bytes, model: str) -> dict:
    b64 = base64.b64encode(image_png).decode()
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": GROUNDED_PROMPT + text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 4000,
        "temperature": 0,
    }


def _correct_page(
    text: str,
    image_png: bytes,
    *,
    model: str,
    api_key: str,
    base_url: str,
    post: Callable,
) -> tuple[str, str | None]:
    """Return (text_out, warning_or_None). Falls back to the anchor text on any
    error or a suspicious-length response — never raises, never loses content."""
    if not text.strip():
        return text, "page not enhanced: no text layer to ground the model"
    try:
        resp = post(
            base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=_build_payload(text, image_png, model),
            timeout=180,
        )
    except Exception as exc:
        return text, f"page not enhanced: request failed ({type(exc).__name__})"
    if getattr(resp, "status_code", 0) != 200:
        return text, f"page not enhanced: HTTP {getattr(resp, 'status_code', '?')}"
    try:
        out = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return text, "page not enhanced: unparseable response"
    if not out:
        return text, "page not enhanced: empty correction"
    ratio = len(out) / max(1, len(text))
    if not (_MIN_RATIO <= ratio <= _MAX_RATIO):
        return text, f"page not enhanced: correction length out of bounds (x{ratio:.2f})"
    return out, None


def enhance_pdf(
    data: bytes,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    max_pages: int | None = None,
    render_scale: float = 2.6,
    post: Callable | None = None,
    render: Callable | None = None,
) -> ExtractResult:
    """Grounded VLM correction of a (typically scanned) PDF, page by page.

    Opt-in only. ``post`` and ``render`` are injectable seams for testing; in
    production they default to httpx + pypdfium2 (the ``[llm]`` extra)."""
    import pdfplumber

    if post is None:
        import httpx

        post = httpx.post
    if render is None:
        import pypdfium2 as pdfium

        def render(pdf_bytes: bytes, index: int, scale: float) -> bytes:
            doc = pdfium.PdfDocument(pdf_bytes)
            img = doc[index].render(scale=scale).to_pil()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    parts: list[str] = []
    warnings: list[str] = []
    corrected = 0
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"could not open PDF: {exc}") from exc
    with pdf:
        n = len(pdf.pages)
        limit = n if max_pages is None else min(n, max_pages)
        for i in range(limit):
            text, _ = page_to_markdown(pdf.pages[i])
            image_png = render(data, i, render_scale)
            out, warn = _correct_page(
                text, image_png, model=model, api_key=api_key, base_url=base_url, post=post
            )
            if warn:
                warnings.append(f"page {i + 1}: {warn}")
            else:
                corrected += 1
            if out.strip():
                parts.append(out)

    return ExtractResult(
        markdown="\n\n".join(parts),
        title=None,
        warnings=[_VERIFY_WARNING, *warnings],
        meta={
            "backend": "pdf+vlm",
            "model": model,
            "pages": limit,
            "pages_corrected": corrected,
            "enhanced": True,
        },
    )
