from scribe.backends.layout import group_lines, words_to_markdown


def _w(t, top, size=10.0, x0=50.0):
    return {"text": t, "x0": x0, "x1": x0 + len(t) * 5, "top": top, "bottom": top + size, "size": size}


def test_group_lines_by_top():
    words = [_w("Hello", 100), _w("world", 100, x0=90), _w("next", 120)]
    lines = group_lines(words)
    assert [" ".join(w["text"] for w in ln) for ln in lines] == ["Hello world", "next"]


def test_heading_detected_by_font_size():
    words = [_w("Big Title", 50, size=20.0)] + [
        _w(f"body{i}", 80 + i * 15, size=10.0) for i in range(5)
    ]
    md = words_to_markdown(words)
    assert md.splitlines()[0].startswith("# ")
    assert "Big Title" in md.splitlines()[0]


def test_paragraph_dehyphenates_wrapped_word():
    words = [_w("hyphen-", 100), _w("ation", 115), _w("continues", 130)]
    md = words_to_markdown(words)
    assert "hyphenation continues" in md


def test_bullet_list_item():
    words = [
        _w("•", 100),
        _w("first", 100, x0=70),
        _w("•", 120),
        _w("second", 120, x0=70),
    ]
    md = words_to_markdown(words)
    assert "- first" in md and "- second" in md
