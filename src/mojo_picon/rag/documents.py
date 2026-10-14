"""Guideline documents as Markdown sections with a locator ("p. 21", "§3") for the citation tag.

PDFs are transcribed page by page (rag/transcribe.py, tables kept); WHO fact sheets come from
their HTML article and the ISSN position stands from Europe PMC's JATS XML. References,
acknowledgements and figures are left out: they are not guidance.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class Section:
    locator: str  # "p. 21" or "§3"; with the document tag it forms the citation tag
    heading: str
    text: str  # Markdown


# --- WHO fact sheets (HTML) ----------------------------------------------------------------

_BLOCKS = {"p", "li", "h2", "h3", "h4", "tr"}
_SKIP_HEADINGS = re.compile(r"referencias|bibliogr", re.I)


class _ArticleParser(HTMLParser):
    """Text of <article class="sf-detail-body-wrapper">, as (heading, paragraphs) blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0  # depth inside the article; 0 = outside
        self.blocks: list[tuple[str, str]] = []  # (tag, text)
        self._tag: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth == 0:
            if tag == "article" and "sf-detail-body-wrapper" in (dict(attrs).get("class") or ""):
                self.depth = 1
            return
        if tag == "article":
            self.depth += 1
        if tag in _BLOCKS:
            self._flush()
            self._tag = tag
        elif tag in {"td", "th"}:
            self._text.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if self.depth == 0:
            return
        if tag in _BLOCKS:
            self._flush()
        if tag == "article":
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and self._tag:
            self._text.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._text)).strip(" |")
        if self._tag and text:
            self.blocks.append((self._tag, text))
        self._tag, self._text = None, []


def html_sections(page: str) -> list[Section]:
    parser = _ArticleParser()
    parser.feed(page)
    parser._flush()
    sections: list[Section] = []
    heading, lines = "", []

    def close() -> None:
        if lines and not _SKIP_HEADINGS.search(heading):
            sections.append(Section(f"§{len(sections) + 1}", heading, "\n".join(lines)))

    for tag, text in parser.blocks:
        if tag == "h2":
            close()
            heading, lines = text, []
        elif tag in {"h3", "h4"}:
            lines.append(f"### {text}")
        else:
            lines.append(f"- {text}" if tag == "li" else text)
    close()
    return sections


# --- ISSN position stands (JATS XML from Europe PMC) ---------------------------------------

_SKIP_SECTIONS = re.compile(r"acknowledg|competing|funding|author|contribution|abbreviation|declaration", re.I)


def jats_sections(xml: str) -> list[Section]:
    """One section per top-level <sec> of the body (with its subsections); abstract first."""
    root = ET.fromstring(xml)
    sections: list[Section] = []
    abstract = root.find(".//front//abstract")
    if abstract is not None:
        sections.append(Section("§0", "Abstract", _jats_markdown(abstract)))
    body = root.find("body")
    for number, sec in enumerate(body.findall("sec") if body is not None else [], start=1):
        title = _text(sec.find("title"))
        if _SKIP_SECTIONS.search(title):
            continue
        sections.append(Section(f"§{number}", title, _jats_markdown(sec, skip_title=True)))
    return [s for s in sections if s.text.strip()]


def _jats_markdown(element: ET.Element, level: int = 2, skip_title: bool = False) -> str:
    out: list[str] = []
    for child in element:
        tag = child.tag
        if tag == "title" and not skip_title:
            out.append(f"{'#' * level} {_text(child)}")
        elif tag == "p":
            out.append(_text(child))
            out.extend(_jats_table(table) for table in child.iter("table-wrap"))  # tables often sit in a <p>
        elif tag == "sec":
            out.append(_jats_markdown(child, level + 1))
        elif tag == "list":
            out.extend(f"- {_text(item)}" for item in child.findall("list-item"))
        elif tag == "table-wrap":
            out.append(_jats_table(child))
    return "\n\n".join(part for part in out if part.strip())


def _jats_table(wrap: ET.Element) -> str:
    caption = _text(wrap.find("caption"))
    rows = [[_text(cell) for cell in row if cell.tag in {"td", "th"}] for row in wrap.iter("tr")]
    rows = [r for r in rows if any(r)]
    if not rows:
        return caption
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = [f"| {' | '.join(rows[0])} |", f"|{'---|' * width}"] + [f"| {' | '.join(r)} |" for r in rows[1:]]
    return "\n".join(([f"**{caption}**"] if caption else []) + lines)


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    # Citations to the reference list ("[12]") are noise for retrieval and for the citation tags
    parts = [t for t in _itertext_without(element, {"xref", "fig", "table-wrap"})]
    return re.sub(r"\s+", " ", html.unescape("".join(parts))).strip()


def _itertext_without(element: ET.Element, skip: set[str]):
    if element.tag in skip:
        return
    if element.text:
        yield element.text
    for child in element:
        if child.tag not in skip:
            yield from _itertext_without(child, skip)
        if child.tail:
            yield child.tail


# --- PDFs (transcribed pages) --------------------------------------------------------------


def page_sections(pages: list[str]) -> list[Section]:
    """Transcribed pages (index 0 = page 1) -> one section per non-empty page."""
    return [Section(f"p. {n}", "", text.strip()) for n, text in enumerate(pages, start=1) if text.strip()]
