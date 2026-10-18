"""PDF pages -> Markdown with Gemini, keeping the tables (RAG: Ingesta). Ingestion only.

A plain text extractor breaks the tables of requirements and servings. Gemini transcribes each
page; the numbers of the transcription are then checked against the text pypdf extracts from the
same page, so a number the model invents or misreads is reported (page_number_mismatches).
The pages are public guidelines: no user data reaches the model here.
"""

from __future__ import annotations

import asyncio
import io
import re

PROMPT = (
    "Transcribe this PDF page to Markdown. Keep headings, lists and tables (as Markdown tables). "
    "Do not summarise, translate, add or change anything; copy every number exactly. "
    "Leave out running headers, footers and page numbers. If the page has no text, answer with nothing."
)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def split_pages(pdf: bytes) -> list[bytes]:
    from pypdf import PdfReader, PdfWriter  # ingestion only: the "data" dependency group

    reader = PdfReader(io.BytesIO(pdf))
    pages = []
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        pages.append(out.getvalue())
    return pages


def page_texts(pdf: bytes) -> list[str]:
    from pypdf import PdfReader  # ingestion only: the "data" dependency group

    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages]


def numbers(text: str) -> set[str]:
    """Numbers as digit strings without separators ("1,200" and "1200" match; "0.8" -> "08")."""
    return {re.sub(r"[.,]", "", n) for n in _NUMBER_RE.findall(text)}


def page_number_mismatches(transcription: str, extracted: str) -> set[str]:
    """Numbers in the transcription that are not in pypdf's text of the same page.

    pypdf often splits a number ("1, 202", "1 ,000"), but a list ("35, 121") looks the same: both
    readings of pypdf's text are accepted."""
    if not extracted.strip():
        return set()
    joined = re.sub(r"(?<=\d) ?([.,]) ?(?=\d)", r"\1", extracted)
    return numbers(transcription) - numbers(extracted) - numbers(joined)


async def transcribe_pages(client, model: str, pages: list[bytes], concurrency: int = 8) -> list[str]:
    """client: google.genai.Client (Vertex AI, EU endpoint)."""
    from google.genai import types

    from mojo_picon.llm import thinking_config

    # Copying a page needs little reasoning, and reasoning tokens are billed as output
    config = types.GenerateContentConfig(
        temperature=0, thinking_config=types.ThinkingConfig(**thinking_config(model, "low"))
    )
    semaphore = asyncio.Semaphore(concurrency)

    async def one(page: bytes) -> str:
        async with semaphore:
            for attempt in range(6):  # the shared quota of Gemini 3 often answers 429 for a while
                try:
                    response = await client.aio.models.generate_content(
                        model=model,
                        contents=[types.Part.from_bytes(data=page, mime_type="application/pdf"), PROMPT],
                        config=config,
                    )
                    return (response.text or "").strip()
                except Exception:
                    if attempt == 5:
                        raise
                    await asyncio.sleep(min(2 ** (attempt + 1), 30))
            return ""

    return list(await asyncio.gather(*(one(p) for p in pages)))
