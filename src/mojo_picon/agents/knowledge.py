"""The expert brief: cached prefix of the Coach's prompt, with source tags (ADR-23)."""

from __future__ import annotations

from pathlib import Path

from mojo_picon.guardrails.number_origin import index_brief

DEFAULT_BRIEF = Path(__file__).resolve().parents[3] / "knowledge" / "expert_brief.md"
PENDING_MARKER = "PENDIENTE DE REDACTAR"


def load_expert_brief(path: Path = DEFAULT_BRIEF) -> tuple[str, dict[str, str]]:
    """(brief text, {citation tag -> lines}). Empty while the author has not written it."""
    if not path.exists():
        return "", {}
    text = path.read_text(encoding="utf-8")
    if PENDING_MARKER in text:
        return "", {}
    return text, index_brief(text)
