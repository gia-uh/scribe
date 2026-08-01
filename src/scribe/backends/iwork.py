"""Apple iWork → Markdown: Pages (`.pages`), Keynote (`.key`), Numbers (`.numbers`).

Two document generations, both handled here. iWork '09 and earlier keep an
`index.xml` / `index.apxl`, parsed with the stdlib. iWork '13 and later keep
`Index/*.iwa`, read by :mod:`._iwa` — see that module for the container
mechanics and this one for what the archives mean.

Headings are decided by paragraph-style *name* first (`Title`, `Heading 2`, …)
and by font size relative to the document's body size second. The second signal
is what carries the feature outside en_US, where the built-in style names are
localised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ..result import ExtractResult
from . import _iwork_tables
from ._iwa import Archive, Container, as_ref, open_container, try_parse

APPS = {"pages": "pages", "key": "keynote", "keynote": "keynote", "numbers": "numbers"}

# --- archive types we interpret (see the design doc for how they were found) --
STORAGE = 2001  # TSWP.StorageArchive        — the text
PARA_STYLE = 2022  # TSWP.ParagraphStyleArchive
LIST_STYLE = 2023  # TSWP.ListStyleArchive
PAGES_DOC = 10000  # TP.DocumentArchive
PAGES_HEADER_FOOTER = 10143  # TP.HeaderFooterStorage
KN_SHOW = 2  # KN.ShowArchive
KN_SLIDE_NODE = 4  # KN.SlideNodeArchive
KN_SLIDE = 5  # KN.SlideArchive
TABLE_INFO = 6000  # TST.TableInfoArchive   — the drawable; `2` is its model
TABLE_MODEL = 6001  # TST.TableModelArchive
GROUP = 2011  # TSD.GroupArchive       — drawables can nest
TN_DOC = 1  # TN.DocumentArchive  (Numbers)
TN_SHEET = 2  # TN.SheetArchive    (Numbers; Keynote reuses 2 for KN.ShowArchive)

# Structural archives a text hunt must not descend into: they lead to the
# stylesheet and to master slides, whose placeholder copy would flood the body.
_OPAQUE = {KN_SHOW, KN_SLIDE_NODE, KN_SLIDE, PARA_STYLE, LIST_STYLE, PAGES_DOC, 401}

_OBJECT_REPLACEMENT = "￼"  # inline attachment marker


@dataclass
class Style:
    name: str | None = None
    size: float | None = None


@dataclass
class Para:
    text: str
    style: Style


# --- shared assembly --------------------------------------------------------

_HEADING_BY_NAME = (
    (re.compile(r"^title\b", re.I), 1),
    (re.compile(r"^sub\s*title\b", re.I), 2),
    (re.compile(r"^heading\s*([1-6])\b", re.I), None),  # level from the digit
    (re.compile(r"^heading\b", re.I), 2),
)
_NEVER_HEADING = re.compile(r"^(body|free form|caption|footnote|default|label)\b", re.I)


def _heading_level(para: Para, body_size: float | None) -> int | None:
    """`None` when the paragraph is body text, else the Markdown heading level."""
    text = para.text.strip()
    if not text:
        return None
    name = (para.style.name or "").strip()
    if name and not _NEVER_HEADING.match(name):
        for pattern, level in _HEADING_BY_NAME:
            m = pattern.match(name)
            if m:
                return min(int(m.group(1)) + 1, 6) if level is None else level
    if name:
        return None  # a named style that is not a heading settles it
    # No usable name (an anonymous style variation, or a localised one we do not
    # recognise): fall back on size, with layout.py's ratios so PDF and iWork
    # documents get headings on the same rule.
    if not body_size or not para.style.size or len(text) > 120:
        return None
    ratio = para.style.size / body_size
    if ratio < 1.15:
        return None
    return 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3


def _body_size(paras: list[Para]) -> float | None:
    """The document's dominant font size, weighted by how much text is set in it."""
    weights: dict[float, int] = {}
    for p in paras:
        if p.style.size:
            weights[p.style.size] = weights.get(p.style.size, 0) + len(p.text.strip())
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: kv[1])[0]


def _render(paras: list[Para]) -> tuple[list[str], str | None]:
    """Paragraphs → Markdown blocks plus the document title (its first level-1
    heading, or failing that its first line)."""
    body_size = _body_size(paras)
    blocks: list[str] = []
    title: str | None = None
    for para in paras:
        text = para.text.strip()
        if not text:
            continue
        level = _heading_level(para, body_size)
        if level == 1 and title is None:
            title = text
        blocks.append(f"{'#' * level} {text}" if level else text)
    if title is None:
        for para in paras:
            if para.text.strip():
                title = para.text.strip()
                break
    return blocks, title


def _clean(text: str) -> str:
    return text.replace(_OBJECT_REPLACEMENT, "").replace(" ", "  \n").strip()


# --- IWA: styles ------------------------------------------------------------


def _resolve_style(container: Container, archive: Archive | None, depth: int = 0) -> Style:
    """A `TSWP.ParagraphStyleArchive` plus whatever it inherits.

    `f1` is the `TSS.StyleArchive` header (`1` display name, `3` parent ref);
    `f11` is the character-property bag, whose `f3` is the font size. Anonymous
    variations carry only the overrides, so a missing value walks up the chain.
    """
    if archive is None or depth > 8:
        return Style()
    header = try_parse(archive.one(1))
    name = None
    if header.get(1) and isinstance(header[1][0], bytes):
        try:
            name = header[1][0].decode()
        except UnicodeDecodeError:
            name = None
    size = None
    char_props = try_parse(archive.one(11))
    if char_props.get(3) and isinstance(char_props[3][0], float):
        size = char_props[3][0]
    if name is not None and size is not None:
        return Style(name, size)
    parent = container.deref(header.get(3, [None])[0]) if header.get(3) else None
    inherited = _resolve_style(container, parent, depth + 1)
    return Style(name if name is not None else inherited.name, size or inherited.size)


def _storage_paragraphs(container: Container, storage: Archive) -> list[Para]:
    """Split a `TSWP.StorageArchive` into paragraphs with a resolved style each.

    `f3` is the text (repeated, concatenated). `f5` is an `ObjectAttributeTable`
    of `{1: character_index, 2: optional style ref}` — the entries partition the
    text, and a missing ref means "no override", i.e. the document default.
    """
    text = "".join(
        v.decode("utf-8", "replace") for v in storage.fields.get(3, []) if isinstance(v, bytes)
    )
    if not text.strip(_OBJECT_REPLACEMENT + " \n\t"):
        return []

    runs: list[tuple[int, Style]] = []
    for entry in try_parse(storage.one(5)).get(1, []):
        e = try_parse(entry)
        idx = e.get(1, [0])[0]
        if not isinstance(idx, int):
            continue
        ref = container.deref(e[2][0]) if e.get(2) else None
        runs.append((idx, _resolve_style(container, ref)))
    runs.sort(key=lambda r: r[0])

    def style_at(pos: int) -> Style:
        found = Style()
        for idx, style in runs:
            if idx > pos:
                break
            found = style
        return found

    paras: list[Para] = []
    offset = 0
    for chunk in text.split("\n"):
        paras.append(Para(_clean(chunk), style_at(offset)))
        offset += len(chunk) + 1
    return paras


def _find_storages(
    container: Container, root: Archive | None, seen: set[int], depth: int = 0
) -> list[Archive]:
    """Every `TSWP.StorageArchive` reachable from ``root``, in encounter order.

    Stops at `_OPAQUE` types so a slide's drawables do not drag in the master
    slide's placeholder copy or the whole stylesheet.
    """
    if root is None or depth > 6 or root.ident in seen:
        return []
    seen.add(root.ident)
    if root.type_id == STORAGE:
        return [root]
    out: list[Archive] = []
    for values in root.fields.values():
        for value in values:
            if not isinstance(value, bytes):
                continue
            target = container.deref(value)
            if target is None:
                for nested in try_parse(value).values():
                    for inner in nested:
                        ref = as_ref(inner)
                        if ref is not None and ref not in seen:
                            child = container.by_id.get(ref)
                            if child and child.type_id not in _OPAQUE:
                                out += _find_storages(container, child, seen, depth + 1)
                continue
            if target.type_id in _OPAQUE:
                continue
            out += _find_storages(container, target, seen, depth + 1)
    return out


# --- IWA: Pages -------------------------------------------------------------


def _convert_pages_iwa(container: Container) -> ExtractResult:
    docs = container.of_type(PAGES_DOC)
    warnings = list(container.warnings)
    paras: list[Para] = []
    seen: set[int] = set()

    body = container.deref(docs[0].one(4)) if docs else None
    if body is not None and body.type_id == STORAGE:
        seen.add(body.ident)
        paras = _storage_paragraphs(container, body)
    else:
        warnings.append("could not locate the document body; text may be out of order")

    # Headers and footers repeat on every page — noise in a note, so drop them.
    for hf in container.of_type(PAGES_HEADER_FOOTER):
        for storage in _find_storages(container, hf, set()):
            seen.add(storage.ident)

    blocks, title = _render(paras)

    # Floating text boxes live outside the body flow; append them after it.
    extras: list[str] = []
    for storage in container.of_type(STORAGE):
        if storage.ident in seen:
            continue
        seen.add(storage.ident)
        extra_blocks, _ = _render(_storage_paragraphs(container, storage))
        extras += extra_blocks
    extras += _table_blocks(container, container.of_type(TABLE_MODEL), warnings)

    return ExtractResult(
        markdown="\n\n".join(blocks + extras),
        title=title,
        warnings=warnings,
        meta={
            "backend": "iwork",
            "app": "pages",
            "generation": "iwa",
            "paragraphs": len(blocks),
        },
    )


# --- IWA: Keynote -----------------------------------------------------------


def _slide_refs(container: Container, show: Archive) -> list[Archive]:
    """The slides in presentation order.

    `KN.ShowArchive.3` is the slide tree; its `f2` entries are the ordered
    `SlideNodeArchive` references, and each node's `f2` is the slide itself.
    Member filenames (`Slide-9283.iwa`) do *not* give this order.
    """
    slides: list[Archive] = []
    for ref in try_parse(show.one(3)).get(2, []):
        node = container.deref(ref)
        if node is None:
            continue
        slide = container.deref(node.one(2)) if node.type_id == KN_SLIDE_NODE else node
        if slide is not None and slide.type_id == KN_SLIDE:
            slides.append(slide)
    return slides


def _master_idents(container: Container, slide: Archive) -> set[int]:
    """The slide's master (`f17`), pre-seeded into a visited set so a table hunt
    does not walk into the theme's placeholder tables."""
    master = container.deref(slide.one(17))
    return {master.ident} if master is not None else set()


def _convert_keynote_iwa(container: Container) -> ExtractResult:
    warnings = list(container.warnings)
    shows = container.of_type(KN_SHOW)
    slides = _slide_refs(container, shows[0]) if shows else []
    if not slides:
        # Master slides sit in their own members; excluding them keeps the
        # theme's "Lorem Ipsum Dolor" placeholders out of the output.
        slides = [a for a in container.of_type(KN_SLIDE) if "MasterSlide" not in a.member]
        if slides:
            warnings.append("slide order could not be determined; using file order")

    parts: list[str] = []
    title: str | None = None
    for number, slide in enumerate(slides, 1):
        seen: set[int] = set()
        heading = f"## Slide {number}"
        body: list[str] = []

        # f5 is the title placeholder, f6 the body placeholder, f42 the ordered
        # drawables; f20 is the presenter-notes drawable.
        title_paras: list[Para] = []
        for storage in _find_storages(container, container.deref(slide.one(5)), seen):
            title_paras += _storage_paragraphs(container, storage)
        slide_title = " ".join(p.text for p in title_paras if p.text).strip()
        if slide_title:
            heading = f"## Slide {number}: {slide_title}"
            if title is None:
                title = slide_title

        for ref in [slide.one(6), *slide.fields.get(42, [])]:
            for storage in _find_storages(container, container.deref(ref), seen):
                for para in _storage_paragraphs(container, storage):
                    if para.text:
                        body.append(f"- {para.text}")

        parts.append(heading)
        parts += body
        parts += _table_blocks(
            container,
            _tables_under(container, slide, _master_idents(container, slide)),
            warnings,
            level="###",
        )

        notes: list[str] = []
        for storage in _find_storages(container, container.deref(slide.one(20)), seen):
            notes += [p.text for p in _storage_paragraphs(container, storage) if p.text]
        if notes:
            parts.append("> **Notes:** " + " ".join(notes))

    return ExtractResult(
        markdown="\n\n".join(parts),
        title=title,
        warnings=warnings,
        meta={"backend": "iwork", "app": "keynote", "generation": "iwa", "slides": len(slides)},
    )


# --- IWA: Numbers -----------------------------------------------------------


def _table_blocks(
    container: Container, tables: list[Archive], warnings: list[str], level: str = "###"
) -> list[str]:
    """Render table models as Markdown, naming each and warning once per reason
    the grid came back empty."""
    blocks: list[str] = []
    for table in tables:
        name = _iwork_tables.table_name(table)
        rows, why = _iwork_tables.table_grid(container, table)
        markdown = _iwork_tables.grid_to_markdown(rows)
        if why and why not in warnings:
            warnings.append(why)
        if not markdown:
            continue
        if name:
            blocks.append(f"{level} {name}")
        blocks.append(markdown)
    return blocks


def _tables_under(
    container: Container, root: Archive | None, seen: set[int], depth: int = 0
) -> list[Archive]:
    """Table models under ``root``, reached only through `TST.TableInfoArchive`.

    A table is always a `TableInfoArchive` drawable whose field 2 is the model.
    Following *any* reference instead leaks: a Numbers sheet links back to
    document-level state, and from there to the other sheets' tables, so every
    table lands under whichever sheet is rendered first.
    """
    if root is None or depth > 4 or root.ident in seen:
        return []
    seen.add(root.ident)
    if root.type_id == TABLE_INFO:
        model = container.deref(root.one(2))
        return [model] if model is not None and model.type_id == TABLE_MODEL else []
    if root.type_id == TABLE_MODEL:
        return [root]
    out: list[Archive] = []
    for values in root.fields.values():  # groups nest drawables
        for value in values:
            target = container.deref(value) if isinstance(value, bytes) else None
            if target is not None and target.type_id in (TABLE_INFO, TABLE_MODEL, GROUP):
                out += _tables_under(container, target, seen, depth + 1)
    return out


def _convert_numbers_iwa(container: Container) -> ExtractResult:
    warnings = list(container.warnings)
    parts: list[str] = []
    title: str | None = None
    claimed: set[int] = set()

    docs = container.of_type(TN_DOC)
    sheets: list[Archive] = []
    if docs:
        for ref in docs[0].fields.get(1, []):
            sheet = container.deref(ref)
            if sheet is not None and sheet.type_id == TN_SHEET:
                sheets.append(sheet)
    if not sheets:
        sheets = container.of_type(TN_SHEET)

    for sheet in sheets:
        raw = sheet.one(1)
        name = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else ""
        if name:
            parts.append(f"## {name}")
            if title is None:
                title = name
        # A sheet's own drawables are field 2. Walking the whole archive instead
        # leaks through document-level references into the *other* sheets' tables.
        tables: list[Archive] = []
        for ref in sheet.fields.get(2, []):
            tables += _tables_under(container, container.deref(ref), claimed)
        claimed |= {t.ident for t in tables}
        parts += _table_blocks(container, tables, warnings)

    # Tables that no sheet claimed (an unusual document shape) still get emitted.
    orphans = [t for t in container.of_type(TABLE_MODEL) if t.ident not in claimed]
    parts += _table_blocks(container, orphans, warnings)

    return ExtractResult(
        markdown="\n\n".join(parts),
        title=title,
        warnings=warnings,
        meta={
            "backend": "iwork",
            "app": "numbers",
            "generation": "iwa",
            "sheets": len(sheets),
            "tables": len(container.of_type(TABLE_MODEL)),
        },
    )


# --- iWork '09 (index.xml / index.apxl) -------------------------------------

_SF = "{http://developer.apple.com/namespaces/sf}"
_SFA = "{http://developer.apple.com/namespaces/sfa}"
_KEY = "{http://developer.apple.com/namespaces/keynote2}"


def _style_names(root: ET.Element) -> dict[str, str]:
    """`sf:ident` → `sf:name` for every declared paragraph style."""
    out: dict[str, str] = {}
    for node in root.iter(f"{_SF}paragraphstyle"):
        ident = node.get(f"{_SF}ident")
        name = node.get(f"{_SF}name")
        if ident and name:
            out[ident] = name
    return out


def _xml_paragraphs(scope: ET.Element, names: dict[str, str]) -> list[Para]:
    paras: list[Para] = []
    for node in scope.iter(f"{_SF}p"):
        text = "".join(node.itertext())
        ident = node.get(f"{_SF}style") or ""
        paras.append(Para(_clean(text), Style(name=names.get(ident))))
    return paras


def _cell09(el: ET.Element) -> str:
    """One iWork '09 datasource cell → its displayed text.

    Text is in a nested `<sf:ct sfa:s="…">`; numbers and formula results are an
    `sf:v` attribute somewhere inside; dates are `sf:cell-date` seconds. A pop-up
    cell carries every menu choice and names the selected one in
    `<sf:proxied-cell-ref>` — taking the first choice instead would put the same
    wrong value in every row of the column.
    """
    proxy = el.find(f".//{_SF}proxied-cell-ref")
    if proxy is not None:
        target = proxy.get(f"{_SFA}IDREF")
        for node in el.iter():
            if node.get(f"{_SFA}ID") == target:
                el = node
                break
    for node in el.iter():
        if node.tag == f"{_SF}ct" and node.get(f"{_SFA}s"):
            return node.get(f"{_SFA}s") or ""
    for node in el.iter():
        seconds = node.get(f"{_SF}cell-date")
        if seconds is not None:
            try:
                return _iwork_tables.seconds_to_date(float(seconds))
            except ValueError:
                return seconds
        raw = node.get(f"{_SF}v")
        if raw is not None:
            try:
                return _iwork_tables.format_number(float(raw))
            except ValueError:
                return raw
    return "".join(el.itertext()).strip()


def _tables09(scope: ET.Element) -> list[tuple[str | None, list[list[str]]]]:
    """`<sf:tabular-model>` grids.

    The datasource is a flat, row-major run of cells — one element per cell,
    except that `sf:col-span` makes a cell occupy several columns. Honouring the
    span is what keeps the grid aligned: `testNumbers.numbers`'s 14×6 table has
    83 cell elements and one 2-column span, which is exactly 84 slots.
    """
    out: list[tuple[str | None, list[list[str]]]] = []
    for model in scope.iter(f"{_SF}tabular-model"):
        grid = model.find(f".//{_SF}grid")
        source = model.find(f".//{_SF}datasource")
        if grid is None or source is None:
            continue
        try:
            width = int(grid.get(f"{_SF}numcols") or 0)
        except ValueError:
            continue
        if width <= 0:
            continue
        rows: list[list[str]] = []
        row: list[str] = []
        for cell in source:
            try:
                span = max(1, int(cell.get(f"{_SF}col-span") or 1))
            except ValueError:
                span = 1
            row.append(_cell09(cell))
            row += [""] * (span - 1)
            while len(row) >= width:
                rows.append(row[:width])
                row = row[width:]
        if row:
            rows.append(row + [""] * (width - len(row)))
        if rows:
            out.append((model.get(f"{_SF}name"), rows))
    return out


def _convert_iwork09(container: Container, app: str) -> ExtractResult:
    try:
        root = ET.fromstring(container.xml or b"")
    except ET.ParseError as exc:
        if container.preview_pdf:
            from . import pdf as pdf_backend

            result = pdf_backend.convert(container.preview_pdf)
            result.warnings.append(
                f"could not read the iWork '09 body ({exc}); converted its PDF preview instead"
            )
            result.meta |= {"app": app, "generation": "iwork09", "via": "preview-pdf"}
            return result
        raise ValueError(f"could not parse the iWork '09 document body: {exc}") from exc

    names = _style_names(root)
    meta = {"backend": "iwork", "app": app, "generation": "iwork09"}

    if app == "keynote":
        parts: list[str] = []
        title: str | None = None
        slides = list(root.iter(f"{_KEY}slide"))
        for number, slide in enumerate(slides, 1):
            notes_root = slide.find(f"{_KEY}notes")
            body = [p for p in _xml_paragraphs(slide, names) if p.text]
            note_paras = _xml_paragraphs(notes_root, names) if notes_root is not None else []
            note_texts = {p.text for p in note_paras if p.text}
            body = [p for p in body if p.text not in note_texts]
            head = body[0].text if body else ""
            parts.append(f"## Slide {number}" + (f": {head}" if head else ""))
            if title is None and head:
                title = head
            parts += [f"- {p.text}" for p in body[1:]]
            for table_name, rows in _tables09(slide):
                markdown = _iwork_tables.grid_to_markdown(rows)
                if markdown:
                    if table_name:
                        parts.append(f"### {table_name}")
                    parts.append(markdown)
            if note_texts:
                parts.append("> **Notes:** " + " ".join(p.text for p in note_paras if p.text))
        return ExtractResult(
            markdown="\n\n".join(parts), title=title, meta=meta | {"slides": len(slides)}
        )

    body_root = root.find(f".//{_SF}text-body")
    paras = _xml_paragraphs(body_root if body_root is not None else root, names)
    blocks, title = _render(paras)

    tables = _tables09(root)
    for name, rows in tables:
        markdown = _iwork_tables.grid_to_markdown(rows)
        if not markdown:
            continue
        if name:
            blocks.append(f"### {name}")
            if title is None:
                title = name
        blocks.append(markdown)

    return ExtractResult(
        markdown="\n\n".join(blocks),
        title=title,
        meta=meta | {"paragraphs": len(blocks), "tables": len(tables)},
    )


# --- entry point ------------------------------------------------------------


def convert(data: bytes, ext: str) -> ExtractResult:
    app = APPS.get(ext.lower().lstrip("."))
    if app is None:
        raise ValueError(f"not an iWork document type: {ext!r}")
    container = open_container(data)
    if container.kind == "iwork09":
        return _convert_iwork09(container, app)
    if app == "pages":
        return _convert_pages_iwa(container)
    if app == "keynote":
        return _convert_keynote_iwa(container)
    return _convert_numbers_iwa(container)
