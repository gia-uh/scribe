import io

from openpyxl import Workbook

from scribe.backends.csv import convert as csv_convert
from scribe.backends.xlsx import convert as xlsx_convert


def _xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "S1"
    ws.append(["Name", "Qty"])
    ws.append(["Apple", 3])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_table():
    md = xlsx_convert(_xlsx()).markdown
    assert "### S1" in md and "| Name | Qty |" in md and "| Apple | 3 |" in md


def test_csv_quoted_commas():
    data = b'Name,Note\n"Smith, J",ok\n'
    md = csv_convert(data).markdown
    assert "| Name | Note |" in md and "| Smith, J | ok |" in md
