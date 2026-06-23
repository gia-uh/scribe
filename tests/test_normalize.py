from scribe.normalize import normalize_text


def test_ligatures_expanded():
    out, _ = normalize_text("oﬃce ﬁle ﬂow aﬀair")  # ﬃ ﬁ ﬂ ﬀ
    assert out.rstrip("\n") == "office file flow affair"


def test_dehyphenation_across_linebreak():
    out, _ = normalize_text("hyphen-\nation works")
    assert "hyphenation works" in out


def test_pua_chars_stripped_and_warned():
    out, warns = normalize_text("cleantext")
    assert out.rstrip("\n") == "cleantext"
    assert any("glyph" in w for w in warns)


def test_nbsp_and_blank_collapse():
    out, _ = normalize_text("a b\n\n\n\n\nc")
    assert "a b" in out
    assert "\n\n\n" not in out


def test_plain_text_untouched():
    out, warns = normalize_text("normal paragraph.\n\nSecond.")
    assert out.rstrip("\n") == "normal paragraph.\n\nSecond."
    assert warns == []
