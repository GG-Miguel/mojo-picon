"""Format of knowledge/expert_brief.md: what index_brief and the output guardrail rely on (ADR-23)."""

import json
import re
from pathlib import Path

from mojo_picon.agents.knowledge import DEFAULT_BRIEF, PENDING_MARKER, load_expert_brief
from mojo_picon.guardrails.number_origin import citations, index_brief

ROOT = Path(__file__).resolve().parents[2]
GUIDE_TAGS = {g["tag"] for g in json.loads((ROOT / "data" / "guides.json").read_text(encoding="utf-8"))}
TEXT = DEFAULT_BRIEF.read_text(encoding="utf-8")
TAG_AT_END = re.compile(r"\[([^\[\]]+)\]\.?$")


def _sections() -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in TEXT.splitlines():
        if line.startswith("## "):
            current = line[3:]
            sections[current] = []
        elif current and line.startswith("- "):
            sections[current].append(line)
    return sections


def _guidance_lines() -> list[str]:
    """Bullets of every section except the last one (when not to answer), which carries no figures."""
    return [line for lines in list(_sections().values())[:-1] for line in lines]


def test_sections_are_numbered_in_order():
    numbers = [int(title.split(".")[0]) for title in _sections()]
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_guidance_line_ends_with_one_source_tag():
    for line in _guidance_lines():
        assert TAG_AT_END.search(line), line
        assert len(citations(line)) == 1, line


def test_every_tag_points_to_a_document_of_the_corpus():
    for line in _guidance_lines():
        tag = TAG_AT_END.search(line).group(1)
        assert tag.rsplit(", ", 1)[0] in GUIDE_TAGS, line


def test_index_has_every_tag():
    index = index_brief(TEXT)
    for line in _guidance_lines():
        assert line in index[TAG_AT_END.search(line).group(1)]


def test_pending_marker_keeps_the_brief_out_of_the_prompt(tmp_path):
    draft = tmp_path / "brief.md"
    draft.write_text(TEXT if PENDING_MARKER in TEXT else f"> {PENDING_MARKER}\n{TEXT}", encoding="utf-8")
    assert load_expert_brief(draft) == ("", {})
    approved = tmp_path / "approved.md"
    approved.write_text(TEXT.replace(PENDING_MARKER, ""), encoding="utf-8")
    brief, passages = load_expert_brief(approved)
    assert brief and passages
