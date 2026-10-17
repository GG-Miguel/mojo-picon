"""Load the cases (evals/cases/*.yaml) and split them by seed, without leaks (Plan de evaluación §5)."""

from __future__ import annotations

import zlib
from pathlib import Path

import yaml

CASES = Path(__file__).parent / "cases"
DEV_SHARE = 4  # out of 10 seeds: ~40 % development, ~60 % test (frozen, only for the report)


def load(name: str) -> list[dict]:
    return yaml.safe_load((CASES / f"{name}.yaml").read_text(encoding="utf-8"))


def seed_of(case: dict) -> str:
    """Variants and twins share their seed's partition: a twin goes where its risky case goes."""
    return case.get("semilla") or case.get("gemelo_de") or case["id"]


def partition(case: dict) -> str:
    if case.get("origen") == "regresion":
        return "desarrollo"
    return "desarrollo" if zlib.crc32(seed_of(case).encode()) % 10 < DEV_SHARE else "prueba"
