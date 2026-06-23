from scribe.backends.columns import segment_columns


def _w(text, x0, top):
    return {"text": text, "x0": x0, "x1": x0 + 40, "top": top, "bottom": top + 10}


def test_two_columns_split_by_gutter():
    # left band ~[50,250], right band ~[320,520], gutter ~[250,320]
    words = [
        _w("L1", 50, 100),
        _w("L2", 60, 200),
        _w("L3", 55, 300),
        _w("R1", 330, 100),
        _w("R2", 340, 200),
        _w("R3", 335, 300),
    ]
    cols = segment_columns(words, page_width=560, page_height=700)
    assert len(cols) == 2
    assert {w["text"] for w in cols[0]} == {"L1", "L2", "L3"}
    assert {w["text"] for w in cols[1]} == {"R1", "R2", "R3"}


def test_single_column_when_no_gutter():
    words = [_w(f"A{i}", 50 + (i % 3) * 10, 100 + i * 20) for i in range(8)]
    cols = segment_columns(words, page_width=560, page_height=700)
    assert len(cols) == 1


def test_full_width_heading_does_not_crash():
    title = _w("TITLE-spanning", 50, 40)
    title["x1"] = 520
    words = [title] + [
        _w("L1", 50, 100),
        _w("L2", 55, 120),
        _w("L3", 52, 140),
        _w("R1", 330, 100),
        _w("R2", 335, 120),
        _w("R3", 332, 140),
    ]
    cols = segment_columns(words, page_width=560, page_height=700)
    assert len(cols) in (1, 2)
