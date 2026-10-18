"""Judge calibration: the author scores the same answers as the judge, blind, and we measure agreement.

uv run --group eval python -m evals.calibrate export evals/results/<run>.json [sheet.md]
    -> a Markdown sheet (by default evals/calibration/hoja.md; it can be written straight into the
       vault): each conversation with its context and empty 1-5 scores, without the judge's
uv run --group eval python -m evals.calibrate compare evals/results/<run>.json [sheet.md]
    -> agreement per criterion: mean absolute difference, exact and ±1 agreement, Cohen's weighted kappa
"""

# ruff: noqa: E501  (this module writes long Markdown lines for the sheet)
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

from evals.cases import load
from evals.metrics import CRITERIA, RUBRIC_VERSION
from evals.review_sheet import food_line, profile_text, quote

SHEET = Path(__file__).parent / "calibration" / "hoja.md"
NAMES = {"adecuacion": "Adecuación", "seguridad": "Seguridad", "uso_de_guias": "Uso de guías", "claridad": "Claridad"}
_CASE = re.compile(r"^## (\S+)")
_SCORE = re.compile(r"^- \*\*(" + "|".join(NAMES.values()) + r")\*\* \(([a-z_]+)\):\s*([1-5])?\s*$")


def _to_five(score: float) -> int:
    """DeepEval's 0-1 score on the 1-5 scale the author uses."""
    return max(1, min(5, round(1 + 4 * score)))


def export(results: Path, sheet: Path = SHEET) -> None:
    rows = json.loads(results.read_text())["results"]["conversations"]
    cases = {c["id"]: c for c in load("conversations")}
    lines = [
        "---", "tags: [evaluacion, juez]", "---", "",
        "# Calibración del juez", "",
        f"Puntúa cada respuesta de **1 (muy mal) a 5 (muy bien)** en los cuatro criterios, **sin mirar las notas del juez** (no están en esta hoja). "
        f"Escribe solo el número después de los dos puntos. Respuestas de la evaluación `{results.name}`; rúbrica del juez {RUBRIC_VERSION}.", "",
        "Después: `uv run --group eval python -m evals.calibrate compare <resultados.json> <esta nota>`.", "",
        "## Criterios", "",
        "Son los mismos pasos que sigue el juez. Si crees que un paso está mal planteado, dilo en el comentario: es lo que ajustará la rúbrica.", "",
    ]  # fmt: skip
    for name, steps in CRITERIA.items():
        lines += [f"**{NAMES[name]}**", "", *[f"{i}. {step}" for i, step in enumerate(steps, 1)], ""]
    lines += ["---", ""]
    for r in rows:
        case = cases.get(r["id"], {})
        today = [food_line(f, g) for f, g in case.get("hoy", {}).items()]
        lines += [f"## {r['id']}", "", f"**Perfil:** {profile_text(case.get('perfil', {}))}", "",
                  f"**Ya registrado hoy:** {'; '.join(today) if today else 'nada'}", ""]  # fmt: skip
        for turn in r["turns"]:
            lines += ["**Usuario:**", "", quote(turn["message"]), "", "**Mojo:**", "", quote(turn["answer"]), ""]
        lines += [
            "**Tu nota (1–5):**",
            "",
            *[f"- **{NAMES[c]}** ({c}): " for c in CRITERIA],
            "",
            "**Comentario:** ",
            "",
            "---",
            "",
        ]
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} conversaciones en {sheet}")


def read_sheet(sheet: Path) -> dict[str, dict[str, int]]:
    """Case id -> criterion -> the author's score (blank scores are left out)."""
    scores: dict[str, dict[str, int]] = {}
    case = None
    for line in sheet.read_text(encoding="utf-8").splitlines():
        if m := _CASE.match(line):
            case = m.group(1)
        elif (m := _SCORE.match(line.strip())) and case and m.group(3):
            scores.setdefault(case, {})[m.group(2)] = int(m.group(3))
    return scores


def _weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float:
    """Cohen's kappa with quadratic weights on a 1..k scale."""
    n = len(a)
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        observed[x - 1][y - 1] += 1 / n
    pa = [sum(row) for row in observed]
    pb = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i, j in itertools.product(range(k), range(k)):
        w = (i - j) ** 2 / (k - 1) ** 2
        num += w * observed[i][j]
        den += w * pa[i] * pb[j]
    return 1 - num / den if den else 1.0


def compare(results: Path, sheet: Path = SHEET) -> None:
    judge = {r["id"]: r.get("judge", {}) for r in json.loads(results.read_text())["results"]["conversations"]}
    author = read_sheet(sheet)
    print("| Criterio | Casos | Diferencia media | Coinciden | ±1 | Kappa ponderado |")
    print("| --- | --- | --- | --- | --- | --- |")
    for criterion in CRITERIA:
        pairs = [(scores[criterion], _to_five(judge[case][criterion]["score"]))
                 for case, scores in author.items() if criterion in scores and criterion in judge.get(case, {})]  # fmt: skip
        if not pairs:
            continue
        a, b = [p[0] for p in pairs], [p[1] for p in pairs]
        mad = sum(abs(x - y) for x, y in pairs) / len(pairs)
        exact = sum(x == y for x, y in pairs)
        near = sum(abs(x - y) <= 1 for x, y in pairs)
        print(f"| {criterion} | {len(pairs)} | {mad:.2f} | {exact} | {near} | {_weighted_kappa(a, b):.2f} |")


if __name__ == "__main__":
    command, results, *rest = sys.argv[1:]
    {"export": export, "compare": compare}[command](Path(results), *(Path(r) for r in rest))
