"""Versioned prompts. Source of truth: these files; scripts/sync_prompts.py uploads them to Langfuse."""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@cache
def load_prompt(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")
