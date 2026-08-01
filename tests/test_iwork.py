"""Apple iWork: Pages, Keynote and Numbers, across both document generations.

Assertions pin *specific* content from each fixture rather than "some text came
out", and several are deliberately discriminating — they fail if a particular
mechanism regresses even though the document still converts:

- `test_keynote_skips_master_slide_placeholders` fails if master slides stop
  being excluded (their placeholder copy floods the body).
- `test_numbers_sheets_do_not_borrow_each_others_tables` fails if the sheet →
  table walk goes back to following every reference.
- `test_iwork09_numbers_grid_is_aligned` fails if `col-span` stops shifting the
  column cursor, because the whole grid slides by one.
- `test_iwork09_popup_cell_uses_the_selected_choice` fails if a pop-up cell
  falls back to the first menu choice, which puts the same value in every row.
"""

from pathlib import Path

import pytest

import scribe
from scribe.backends import _iwa

C = Path(__file__).parent / "corpus"


def _convert(name):
    return scribe.from_path(C / name)


# --- container mechanics ----------------------------------------------------


def test_snappy_literal_and_copy():
    # varint(15) | literal "ab" | 3x copy(len=4, offset=2), self-overlapping | literal "c"
    block = bytes([15, (1 << 2) | 0, ord("a"), ord("b")])
    block += bytes([(4 - 4) << 2 | 1, 2]) * 3
    block += bytes([(0 << 2) | 0, ord("c")])
    assert _iwa.snappy_decompress(block) == b"ab" * 7 + b"c"


def test_snappy_rejects_a_truncated_block():
    with pytest.raises(ValueError, match="expected"):
        _iwa.snappy_decompress(bytes([20, (1 << 2) | 0, ord("a"), ord("b")]))


def test_parse_fields_reads_each_wire_type():
    buf = bytes([0x08, 0x96, 0x01]) + bytes([0x12, 0x02]) + b"hi" + bytes([0x25, 0, 0, 0x80, 0x3F])
    fields = _iwa.parse_fields(buf)
    assert fields[1] == [150] and fields[2] == [b"hi"] and fields[4] == [1.0]


def test_as_ref_only_matches_a_bare_identifier_message():
    assert _iwa.as_ref(bytes([0x08, 0x2A])) == 42
    assert _iwa.as_ref(bytes([0x08, 0x2A, 0x10, 0x01])) is None  # two fields: not a reference
    assert _iwa.as_ref(b"plain text") is None


def test_package_shaped_document_is_read():
    """iwork13.key is saved as a package: the real index is a nested Index.zip."""
    container = _iwa.open_container((C / "iwork13.key").read_bytes())
    assert container.kind == "iwa"
    assert any("Index.zip!" in a.member for a in container.archives)


def test_password_protected_document_says_so():
    with pytest.raises(ValueError, match="password-protected"):
        _convert("iwork_protected.pages")


def test_dispatch_by_extension():
    data = (C / "iwork13.pages").read_bytes()
    assert scribe.to_markdown(data, filename="whatever.pages").meta["backend"] == "iwork"


# --- Pages ------------------------------------------------------------------


def test_pages_iwa_body_text_in_reading_order():
    result = _convert("iwork13.pages")
    md = result.markdown
    assert result.meta["generation"] == "iwa"
    assert result.title == "Sample pages document"
    assert "Some plain text to parse." in md
    assert md.index("Some plain text to parse.") < md.index("The Keynote APXL file")


def test_pages_iwork09_headings_come_from_style_names():
    result = _convert("iwork09.pages")
    md = result.markdown
    assert result.meta["generation"] == "iwork09"
    assert "# Lorem ipsum dolor sit amet" in md  # style "Title"
    assert "## Consectetur adipiscing elit" in md  # style "Heading 1"
    assert "### Duis aute in voluptate velit esse" in md  # style "Heading 2"


def test_pages_body_paragraphs_are_not_headings():
    md = _convert("iwork09.pages").markdown
    body = "Eset eiusmod tempor incidunt et labore"
    assert body in md and f"# {body}" not in md


# --- Keynote ----------------------------------------------------------------


def test_keynote_slides_are_numbered_in_presentation_order():
    result = _convert("iwork13.key")
    md = result.markdown
    assert result.meta["slides"] == 2
    assert "## Slide 1: Libreoffice 6.2" in md
    assert "## Slide 2: Test running..." in md
    assert md.index("Libreoffice 6.2") < md.index("Windows 10 x86")


def test_keynote_skips_master_slide_placeholders():
    """The theme's 12 master slides carry Indonesian placeholder copy. If master
    skipping regresses it lands in the body and swamps the two real slides."""
    md = _convert("iwork13.key").markdown
    assert "Teks Judul" not in md
    assert "Johnny Appleseed" not in md
    assert "Level Badan Satu" not in md


def test_keynote_iwork09_slides_and_speaker_notes():
    result = _convert("iwork09.key")
    md = result.markdown
    assert result.meta["generation"] == "iwork09"
    assert "## Slide 1: A sample presentation" in md
    assert "> **Notes:** A nice note" in md
    assert "Some random text for the sake of testability." in md


# --- Numbers ----------------------------------------------------------------


def test_numbers_v5_grid_including_the_blank_cells():
    md = _convert("iwork13.numbers").markdown
    assert "### ZZZ_Table_1" in md
    assert "| YYY_ROW_1 | YYY_1_1 | YYY_1_2 |" in md
    # XXX_Table_1 has two deliberately empty cells; they must stay empty, in place.
    assert "| XXX_ROW_2 | XXX_2_1 | XXX_2_2 |  | XXX_2_4 | XXX_2_5 |" in md
    assert "| XXX_ROW_3 | XXX_3_1 |  | XXX_3_3 | XXX_3_4 | XXX_3_5 |" in md


def test_numbers_sheets_do_not_borrow_each_others_tables():
    md = _convert("iwork13.numbers").markdown
    assert md.index("## ZZZ_Sheet_2") < md.index("### XXX_Table_1")
    assert md.count("### XXX_Table_1") == 1


def test_iwork09_numbers_grid_is_aligned():
    """A row of the Transactions table, whole. The running Balance column is its
    own checksum: 4650 − 775 = 3875, and every later row follows from the one
    above, so a single misplaced cell breaks the arithmetic."""
    md = _convert("iwork09.numbers").markdown
    assert "| Type | Date | Description | Category | Amount | Balance |" in md
    assert "| 101 | 2009-10-01 | Rent | Home | -775 | 3875 |" in md
    assert "| 102 | 2009-10-15 | Utilities | Home | -97.4 | 3777.6 |" in md


def test_iwork09_popup_cell_uses_the_selected_choice():
    """"Deposit" is the *first* menu choice of every pop-up cell in the Category
    column, so falling back to it would make the column uniform. These two rows
    select different choices, and one of them does select Deposit."""
    md = _convert("iwork09.numbers").markdown
    assert "| Debit Card | 2009-10-22 | Groceries | Food | -101 | 3601.6 |" in md
    assert "| DEP | 2009-10-29 | Insurance refund | Deposit | 135 | 3576.6 |" in md


def test_iwork09_numbers_formula_results_are_rendered():
    md = _convert("iwork09.numbers").markdown
    assert "| Home | -872.4 |" in md  # =SUMIF(...) result, not the formula text


# --- honest degradation -----------------------------------------------------


def test_undecodable_cell_storage_warns_rather_than_guessing():
    result = _convert("iwork13.pages")
    assert any("not decode" in w for w in result.warnings)
    assert result.markdown  # the text still converted
