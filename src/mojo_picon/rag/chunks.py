"""Sections -> chunks of about MAX_CHARS, split at paragraph boundaries; a table is never split.

Each chunk keeps the metadata of its document (RAG: fuente, sección, página, año y licencia) and a
citation tag "<document tag>, <locator>" ("EFSA DRV 2017, p. 21"), the same format as the expert
brief, so the output guardian can check a cited number against the chunk (ADR-19).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass

from mojo_picon.rag.documents import Section

MAX_CHARS = 2400  # about 600 tokens; the size is one of the RAG experiments (milestone 2)
NAMESPACE = uuid.UUID("5f0b8f9e-4a43-4d1d-9b8e-6d0a7c2b1e11")  # stable point ids across rebuilds


@dataclass(frozen=True)
class Chunk:
    tag: str
    text: str
    doc_id: str
    title: str
    heading: str
    locator: str
    year: int
    license: str
    url: str
    language: str

    @property
    def point_id(self) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{self.tag}#{self.text[:200]}"))

    def payload(self) -> dict:
        return asdict(self)


def chunk_document(guide: dict, sections: list[Section], max_chars: int = MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        parts = _split(section.text, max_chars)
        for i, text in enumerate(parts):
            locator = section.locator if len(parts) == 1 else f"{section.locator}.{i + 1}"
            # The heading travels with every piece of its section: it is often what the query matches
            body = f"## {section.heading}\n\n{text}" if section.heading else text
            chunks.append(
                Chunk(
                    tag=f"{guide['tag']}, {locator}",
                    text=body,
                    doc_id=guide["id"],
                    title=guide["title"],
                    heading=section.heading,
                    locator=locator,
                    year=guide["year"],
                    license=guide["license"],
                    url=f"https://doi.org/{guide['doi']}" if guide.get("doi") else guide["url"],
                    language=guide["language"],
                )
            )
    return chunks


def _split(text: str, max_chars: int) -> list[str]:
    blocks = _blocks(text)
    parts: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) + 2 > max_chars:
            parts.append(current)
            current = ""
        if len(block) > max_chars and not _is_table(block):
            # A very long paragraph: cut at sentence ends
            for sentence in re.split(r"(?<=[.!?])\s+", block):
                if current and len(current) + len(sentence) + 1 > max_chars:
                    parts.append(current)
                    current = ""
                current = f"{current} {sentence}".strip()
            continue
        current = f"{current}\n\n{block}" if current else block
    if current:
        parts.append(current)
    return parts


def _blocks(text: str) -> list[str]:
    """Paragraphs, with each Markdown table (consecutive "|" lines) kept as one block."""
    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        lines = paragraph.splitlines()
        table: list[str] = []
        other: list[str] = []
        for line in lines:
            if line.lstrip().startswith("|"):
                if other:
                    blocks.append("\n".join(other))
                    other = []
                table.append(line)
            else:
                if table:
                    blocks.append("\n".join(table))
                    table = []
                other.append(line)
        for rest in (table, other):
            if rest:
                blocks.append("\n".join(rest))
    return [b for b in blocks if b.strip()]


def _is_table(block: str) -> bool:
    return block.lstrip().startswith("|")
