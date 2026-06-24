"""Tests for the opt-in VLM enhancer. No network: the HTTP `post` and image
`render` seams are injected with fakes, so these are fully deterministic."""

from pathlib import Path

from scribe.enhance import _correct_page, enhance_pdf

UGLY = (Path(__file__).parent / "corpus" / "ugly.pdf").read_bytes()


def _resp(content, status=200):
    class R:
        status_code = status

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    return R()


def _fake_render(data, index, scale):
    return b"\x89PNG-fake"


# --- _correct_page unit behavior ---


def test_correct_page_applies_clean_correction():
    post = lambda *a, **k: _resp("ARTICULO 1.-Se declara ilícita la Ley alguno.")  # noqa: E731
    out, warn = _correct_page(
        "ARTJCULO 1.-Se declara ilicita la Ley almno.",
        b"img",
        model="m",
        api_key="k",
        base_url="u",
        post=post,
    )
    assert warn is None
    assert out == "ARTICULO 1.-Se declara ilícita la Ley alguno."


def test_correct_page_rejects_runaway_length_keeps_anchor():
    anchor = "Short anchor text."
    post = lambda *a, **k: _resp("x " * 500)  # 1000 chars vs ~18 → off-rails  # noqa: E731
    out, warn = _correct_page(anchor, b"i", model="m", api_key="k", base_url="u", post=post)
    assert out == anchor
    assert warn and "length out of bounds" in warn


def test_correct_page_http_error_keeps_anchor():
    anchor = "Anchor."
    post = lambda *a, **k: _resp("ignored", status=429)  # noqa: E731
    out, warn = _correct_page(anchor, b"i", model="m", api_key="k", base_url="u", post=post)
    assert out == anchor and "HTTP 429" in warn


def test_correct_page_request_exception_keeps_anchor():
    def boom(*a, **k):
        raise RuntimeError("network down")

    out, warn = _correct_page("Anchor.", b"i", model="m", api_key="k", base_url="u", post=boom)
    assert out == "Anchor." and "request failed" in warn


def test_correct_page_empty_text_not_enhanced():
    out, warn = _correct_page("   ", b"i", model="m", api_key="k", base_url="u", post=lambda *a, **k: _resp("x"))
    assert "no text layer" in warn


# --- enhance_pdf orchestration ---


def test_enhance_pdf_corrects_and_tags(monkeypatch):
    # Fake corrector: uppercase the anchor so we can detect it ran.
    def post(url, headers, json, timeout):
        anchor = json["messages"][0]["content"][0]["text"]
        body = anchor.split("OCR TEXT:\n", 1)[-1]
        return _resp(body.upper())

    r = enhance_pdf(UGLY, api_key="k", post=post, render=_fake_render, max_pages=1)
    assert r.meta["enhanced"] is True
    assert r.meta["backend"] == "pdf+vlm"
    assert r.meta["pages"] == 1
    assert r.meta["pages_corrected"] == 1
    assert r.warnings[0].startswith("AI-assisted correction")
    assert "GACETA" in r.markdown.upper()  # page-1 content, uppercased by fake corrector


def test_enhance_pdf_degrades_gracefully_on_api_failure():
    def post(*a, **k):
        return _resp("", status=500)

    r = enhance_pdf(UGLY, api_key="k", post=post, render=_fake_render, max_pages=2)
    # Falls back to deterministic text; never crashes; flags every page.
    assert r.meta["pages_corrected"] == 0
    assert "GACETA" in r.markdown  # raw OCR preserved
    assert any("HTTP 500" in w for w in r.warnings)
