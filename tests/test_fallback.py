from scribe.api import to_markdown
from scribe.backends import fallback


def test_supports_long_tail():
    assert fallback.supports("html") and fallback.supports("epub") and fallback.supports("rtf")
    assert not fallback.supports("pdf")  # pdf has a native backend


def test_html_via_fallback():
    html = b"<h1>Hi</h1><p>body</p>"
    md = to_markdown(html, ext="html").markdown
    assert "Hi" in md and "body" in md


def test_txt_passthrough_and_normalized():
    # ligature must be fixed by the pipeline's normalizer
    assert "office" in to_markdown("oﬃce hours".encode(), ext="txt").markdown


def test_url_requires_http():
    import pytest

    with pytest.raises(ValueError):
        fallback.convert_url("ftp://nope")
