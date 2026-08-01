"""The iWork container: zip layout, IWA framing, Snappy, protobuf wire walk.

Apple's `.pages` / `.key` / `.numbers` are zips. Since iWork '13 the payload is
`Index/*.iwa`: chunks of raw-Snappy-compressed protobuf. This module reads that
without `python-snappy` (which needs the C libsnappy) and without the `protobuf`
runtime and its ~9 MB of generated iWork schema classes — a generic wire-format
walk plus a handful of field numbers is enough for text, and it keeps scribe
installable with no compiled extras.

The `iwork` backend on top interprets the archives; everything here is format
mechanics.
"""

from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass, field

# --- Snappy -----------------------------------------------------------------


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    val = shift = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def snappy_decompress(data: bytes) -> bytes:
    """Decompress one raw Snappy block (no stream framing)."""
    expected, i = _varint(data, 0)
    out = bytearray()
    end = len(data)
    while i < end:
        tag = data[i]
        i += 1
        kind = tag & 0x03
        if kind == 0:  # literal
            ln = tag >> 2
            if ln >= 60:
                extra = ln - 59
                ln = int.from_bytes(data[i : i + extra], "little")
                i += extra
            ln += 1
            out += data[i : i + ln]
            i += ln
            continue
        if kind == 1:  # copy, 1-byte offset
            ln = 4 + ((tag >> 2) & 0x07)
            off = ((tag >> 5) << 8) | data[i]
            i += 1
        elif kind == 2:  # copy, 2-byte offset
            ln = (tag >> 2) + 1
            off = int.from_bytes(data[i : i + 2], "little")
            i += 2
        else:  # copy, 4-byte offset
            ln = (tag >> 2) + 1
            off = int.from_bytes(data[i : i + 4], "little")
            i += 4
        if off <= 0 or off > len(out):
            raise ValueError("snappy: copy offset out of range")
        start = len(out) - off
        for k in range(ln):  # byte-wise: copies may overlap themselves
            out.append(out[start + k])
    if len(out) != expected:
        raise ValueError(f"snappy: expected {expected} bytes, got {len(out)}")
    return bytes(out)


def iwa_decompress(data: bytes) -> bytes:
    """Concatenate every Snappy chunk of one `.iwa` member.

    Framing is a 4-byte header per chunk: `0x00` then a 3-byte little-endian
    compressed length.
    """
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        if data[i] != 0x00:
            raise ValueError(f"iwa: bad chunk header 0x{data[i]:02x} at offset {i}")
        ln = int.from_bytes(data[i + 1 : i + 4], "little")
        i += 4
        out += snappy_decompress(data[i : i + ln])
        i += ln
    return bytes(out)


# --- protobuf ---------------------------------------------------------------


def parse_fields(buf: bytes) -> dict[int, list]:
    """Generic wire-format walk → ``{field_number: [value, ...]}``.

    Length-delimited values stay raw ``bytes`` (they may be a nested message, a
    UTF-8 string or a packed array — only the caller knows which).
    """
    out: dict[int, list] = {}
    i = 0
    n = len(buf)
    while i < n:
        key, i = _varint(buf, i)
        fno, wt = key >> 3, key & 0x07
        if wt == 0:
            v, i = _varint(buf, i)
        elif wt == 1:
            v = struct.unpack_from("<d", buf, i)[0]
            i += 8
        elif wt == 2:
            ln, i = _varint(buf, i)
            if i + ln > n:
                raise ValueError("protobuf: length-delimited field runs past the end")
            v = buf[i : i + ln]
            i += ln
        elif wt == 5:
            v = struct.unpack_from("<f", buf, i)[0]
            i += 4
        else:  # 3/4 are the deprecated groups, 6/7 are not assigned
            raise ValueError(f"protobuf: unsupported wire type {wt}")
        out.setdefault(fno, []).append(v)
    return out


def try_parse(buf) -> dict[int, list]:
    """``parse_fields`` that yields ``{}`` instead of raising — for probing a
    value that may or may not be a nested message."""
    if not isinstance(buf, bytes):
        return {}
    try:
        return parse_fields(buf)
    except (ValueError, IndexError, struct.error):
        return {}


def as_ref(value) -> int | None:
    """A ``TSP.Reference`` is a message whose only field is ``1: <identifier>``."""
    fields = try_parse(value)
    if list(fields) != [1] or len(fields[1]) != 1:
        return None
    ident = fields[1][0]
    return ident if isinstance(ident, int) else None


# --- the archive graph ------------------------------------------------------


@dataclass
class Archive:
    ident: int
    type_id: int
    payload: bytes
    member: str

    _fields: dict[int, list] | None = field(default=None, repr=False, compare=False)

    @property
    def fields(self) -> dict[int, list]:
        if self._fields is None:
            self._fields = try_parse(self.payload)
        return self._fields

    def one(self, fno: int):
        vals = self.fields.get(fno)
        return vals[0] if vals else None


def read_archives(stream: bytes, member: str) -> list[Archive]:
    """Split a decompressed `.iwa` stream into archives.

    Layout is ``varint(len) ArchiveInfo`` followed by one payload per
    ``ArchiveInfo.message_infos`` entry, in order.
    """
    out: list[Archive] = []
    i = 0
    n = len(stream)
    while i < n:
        ln, i = _varint(stream, i)
        info = parse_fields(stream[i : i + ln])
        i += ln
        ident = info.get(1, [0])[0]
        for raw in info.get(2, []):
            mi = try_parse(raw)
            type_id = mi.get(1, [0])[0]
            length = mi.get(3, [0])[0]
            out.append(Archive(ident, type_id, stream[i : i + length], member))
            i += length
    return out


@dataclass
class Container:
    """One opened iWork document."""

    kind: str  # "iwa" | "iwork09"
    archives: list[Archive] = field(default_factory=list)
    by_id: dict[int, Archive] = field(default_factory=dict)
    xml: bytes | None = None  # iwork09: the index.xml / index.apxl body
    preview_pdf: bytes | None = None  # iwork09 only; '13+ ships JPEGs
    warnings: list[str] = field(default_factory=list)

    def of_type(self, type_id: int) -> list[Archive]:
        return [a for a in self.archives if a.type_id == type_id]

    def deref(self, value) -> Archive | None:
        ident = as_ref(value)
        return self.by_id.get(ident) if ident is not None else None


_XML_MEMBERS = ("index.xml", "index.apxl", "index.xml.gz", "index.apxl.gz")


def _iwa_members(zf: zipfile.ZipFile) -> dict[str, bytes]:
    """Every `.iwa` in the zip, following the package shape where the real index
    is a nested `Foo.key/Index.zip`."""
    out: dict[str, bytes] = {}
    for name in zf.namelist():
        if name.endswith(".iwa"):
            out[name] = zf.read(name)
        elif name.endswith("Index.zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(zf.read(name))) as inner:
                    for iname in inner.namelist():
                        if iname.endswith(".iwa"):
                            out[f"{name}!{iname}"] = inner.read(iname)
            except zipfile.BadZipFile:
                continue
    return out


def _find_member(zf: zipfile.ZipFile, wanted: tuple[str, ...]) -> str | None:
    """Locate one of ``wanted`` at the zip root or one directory down (the
    package shape nests everything under ``Foo.pages/``)."""
    for name in zf.namelist():
        tail = name.rsplit("/", 1)[-1]
        if tail in wanted and name.count("/") <= 1:
            return name
    return None


def open_container(data: bytes) -> Container:
    """Detect and read an iWork document. Raises ``ValueError`` when the bytes
    are not a readable iWork zip (including the password-protected case, which
    is reported with its own message)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a readable iWork document: {exc}") from exc

    with zf:
        if _is_encrypted(zf):
            raise ValueError(
                "the document is password-protected; open it in iWork and save an "
                "unprotected copy first"
            )

        members = _iwa_members(zf)
        if members:
            container = Container(kind="iwa")
            for name in sorted(members):
                try:
                    stream = iwa_decompress(members[name])
                except (ValueError, IndexError) as exc:
                    container.warnings.append(f"could not read {name}: {exc}")
                    continue
                try:
                    archives = read_archives(stream, name)
                except (ValueError, IndexError, struct.error) as exc:
                    container.warnings.append(f"could not read {name}: {exc}")
                    continue
                container.archives.extend(archives)
            for a in container.archives:
                container.by_id.setdefault(a.ident, a)
            if not container.archives:
                raise ValueError(
                    "no readable iWork archives in the document — it may be "
                    "password-protected or corrupt"
                )
            return container

        xml_member = _find_member(zf, _XML_MEMBERS)
        if xml_member:
            raw = zf.read(xml_member)
            if xml_member.endswith(".gz"):
                import gzip

                raw = gzip.decompress(raw)
            preview = _find_member(zf, ("Preview.pdf",)) or next(
                (n for n in zf.namelist() if n.endswith("QuickLook/Preview.pdf")), None
            )
            return Container(
                kind="iwork09",
                xml=raw,
                preview_pdf=zf.read(preview) if preview else None,
            )

    raise ValueError("not an iWork document (no Index/*.iwa and no index.xml)")


def _is_encrypted(zf: zipfile.ZipFile) -> bool:
    """A password-protected iWork document encrypts its members in place.

    iWork does not use standard zip encryption; it substitutes its own
    compression methods (0x636B / 0x636C, `"ck"` / `"cl"`), which is what
    `testPagesPwdProtected.pages` carries and what makes `zipfile.read` raise
    `NotImplementedError`. Anything outside stored/deflated means we cannot get
    at the bytes — checking the zip's own encryption flag too costs nothing.
    """
    for info in zf.infolist():
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            return True
        if info.flag_bits & 0x1:
            return True
    return False
