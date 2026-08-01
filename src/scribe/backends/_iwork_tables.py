"""iWork tables: `TST.TableModelArchive` → a grid of rendered cell values.

Shared by Numbers, and by tables embedded in Pages documents and Keynote slides —
all three store a table the same way.

Cell values live in a tiled binary store. Each cell is a little header followed by
whatever the flags word says is present, so this decoder reads **by flags rather
than by declared cell type**: a `string_id` means look the text up in the table's
string list, a `seconds` double means a date, a decimal128 or double means a
number. Getting the type enum wrong is then impossible, because it is never
consulted.

Only storage **version 5** is decoded — the layout every Numbers since 2020
writes. Older documents (the 2013–2016 "pre-BNC" version 4) have a different
value layout; they yield an empty grid and the caller warns, rather than
rendering numbers that might be wrong.
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone

from ._iwa import Archive, Container, try_parse

TILE = 6002
DATA_LIST = 6005

_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
_DECIMAL128_BIAS = 0x1820

# Cell-storage flag bits, in the order their payloads are laid out.
_FLAG_WIDTHS = (
    (0x1, 16),  # decimal128
    (0x2, 8),  # double
    (0x4, 8),  # seconds since 2001-01-01
    (0x8, 4),  # string id
    (0x10, 4),  # rich-text id
    (0x20, 4),  # cell style id
    (0x40, 4),  # text style id
    (0x80, 4),
    (0x100, 4),
    (0x200, 4),  # formula id
    (0x400, 4),  # control id
    (0x800, 4),
    (0x1000, 4),  # suggest id
    (0x2000, 4),  # number format id
    (0x4000, 4),  # currency format id
    (0x8000, 4),  # date format id
    (0x10000, 4),  # duration format id
    (0x20000, 4),  # text format id
    (0x40000, 4),  # bool format id
)


def _decimal128(buf: bytes) -> float:
    """IEEE 754-2008 decimal128, binary-integer-significand encoding."""
    exp = (((buf[15] & 0x7F) << 7) | (buf[14] >> 1)) - _DECIMAL128_BIAS
    mantissa = buf[14] & 1
    for i in range(13, -1, -1):
        mantissa = mantissa * 256 + buf[i]
    if buf[15] & 0x80:
        mantissa = -mantissa
    return float(mantissa * 10**exp)


def format_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:g}"


def seconds_to_date(seconds: float) -> str:
    """iWork stores instants as seconds from 2001-01-01 UTC."""
    return (_EPOCH + timedelta(seconds=seconds)).date().isoformat()


def _decode_cell(buf: bytes) -> dict:
    """One version-5 cell → the values its flags say are present."""
    if len(buf) < 12 or buf[0] != 5:
        return {}
    flags = struct.unpack_from("<i", buf, 8)[0]
    out: dict = {}
    offset = 12
    for bit, width in _FLAG_WIDTHS:
        if not flags & bit:
            continue
        chunk = buf[offset : offset + width]
        if len(chunk) < width:
            return out
        if bit == 0x1:
            out["number"] = _decimal128(chunk)
        elif bit == 0x2:
            out.setdefault("number", struct.unpack("<d", chunk)[0])
        elif bit == 0x4:
            out["seconds"] = struct.unpack("<d", chunk)[0]
        elif bit == 0x8:
            out["string_id"] = struct.unpack("<i", chunk)[0]
        elif bit == 0x10:
            out["rich_id"] = struct.unpack("<i", chunk)[0]
        offset += width
    return out


def _render_cell(cell: dict, strings: dict[int, str], rich: dict[int, str]) -> str:
    if "string_id" in cell:
        return strings.get(cell["string_id"], "")
    if "rich_id" in cell:
        return rich.get(cell["rich_id"], "")
    if "seconds" in cell:
        try:
            return seconds_to_date(cell["seconds"])
        except (OverflowError, ValueError):
            return ""
    if "number" in cell:
        return format_number(cell["number"])
    return ""


def _data_list(container: Container, ref) -> dict[int, str]:
    """A `TST.DataList` → `{key: text}`, following a reference when the entry
    holds a text storage rather than a plain string."""
    archive = container.deref(ref)
    if archive is None or archive.type_id != DATA_LIST:
        return {}
    out: dict[int, str] = {}
    for raw in archive.fields.get(3, []):
        entry = try_parse(raw)
        key = entry.get(1, [None])[0]
        if not isinstance(key, int):
            continue
        for values in entry.values():
            for value in values:
                if isinstance(value, bytes):
                    try:
                        text = value.decode()
                    except UnicodeDecodeError:
                        continue
                    if text:
                        out.setdefault(key, text)
    return out


def _rich_text(container: Container, store: dict[int, list], skip) -> dict[int, str]:
    """Rich-text cells point into a separate list whose entries reference a
    `TSWP.StorageArchive`. Which list it is varies, so merge every candidate."""
    from .iwork import STORAGE

    out: dict[int, str] = {}
    for fno, values in store.items():
        if fno in (3, 4) or not values:
            continue
        archive = container.deref(values[0])
        if archive is None or archive.type_id != DATA_LIST or archive is skip:
            continue
        for raw in archive.fields.get(3, []):
            entry = try_parse(raw)
            key = entry.get(1, [None])[0]
            if not isinstance(key, int):
                continue
            for inner in entry.values():
                for value in inner:
                    target = container.deref(value) if isinstance(value, bytes) else None
                    if target is not None and target.type_id == STORAGE:
                        text = "".join(
                            v.decode("utf-8", "replace")
                            for v in target.fields.get(3, [])
                            if isinstance(v, bytes)
                        )
                        if text.strip():
                            out.setdefault(key, text.strip())
    return out


def table_name(table: Archive) -> str | None:
    """`TST.TableModelArchive.8` is the user-visible name (`1` is a UUID)."""
    raw = table.one(8)
    if isinstance(raw, bytes):
        try:
            name = raw.decode().strip()
        except UnicodeDecodeError:
            return None
        return name or None
    return None


def table_grid(container: Container, table: Archive) -> tuple[list[list[str]], str | None]:
    """``(rows, warning)`` for one table model — an empty grid plus a reason when
    the cell store is a version this reader does not decode."""
    store = try_parse(table.one(4))
    if not store:
        return [], "table data store is unreadable"

    strings = _data_list(container, store.get(4, [None])[0])
    rich = _rich_text(container, store, container.deref(store.get(4, [None])[0]))

    n_rows = table.one(6) if isinstance(table.one(6), int) else 0
    n_cols = table.one(7) if isinstance(table.one(7), int) else 0

    tiles: list[tuple[int, Archive]] = []
    for raw in try_parse(store.get(3, [None])[0]).get(1, []):
        entry = try_parse(raw)
        archive = container.deref(entry.get(2, [None])[0])
        index = entry.get(1, [0])[0]
        if archive is not None and archive.type_id == TILE:
            tiles.append((index if isinstance(index, int) else 0, archive))
    tiles.sort(key=lambda t: t[0])

    rows: list[list[str]] = []
    unsupported: int | None = None
    for _, tile in tiles:
        for raw in tile.fields.get(5, []):
            info = try_parse(raw)
            version = info.get(5, [0])[0]
            if version != 5:
                unsupported = version
                continue
            buffer = info.get(6, [b""])[0]
            offsets = info.get(7, [b""])[0]
            if not buffer or len(offsets) < 2:
                continue
            starts = struct.unpack(f"<{len(offsets) // 2}h", offsets)
            used = sorted((o, c) for c, o in enumerate(starts) if o >= 0)
            row = [""] * max(n_cols, (max(c for _, c in used) + 1) if used else 0)
            for i, (start, col) in enumerate(used):
                end = used[i + 1][0] if i + 1 < len(used) else len(buffer)
                text = _render_cell(_decode_cell(buffer[start:end]), strings, rich)
                if col < len(row):
                    row[col] = text
            rows.append(row)

    if n_rows:
        rows = rows[:n_rows]
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    if not rows and unsupported is not None:
        return [], (
            "some table cells are stored in an iWork cell format this reader does "
            f"not decode (version {unsupported}, written by iWork 2013–2016) and were skipped"
        )
    return rows, None


def grid_to_markdown(rows: list[list[str]]) -> str:
    """First row as the header, matching what the xlsx backend emits."""
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [[c.replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (width - len(r)) for r in rows]
    head, *body = rows
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] * width) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)
