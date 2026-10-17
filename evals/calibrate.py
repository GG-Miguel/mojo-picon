"""Judge calibration: the author scores the same answers as the judge, blind, and we measure agreement.

uv run --group eval python -m evals.calibrate export evals/results/<run>.json
    -> evals/calibration/hoja.yaml: the conversations and empty scores (1-5), without the judge's
(the author fills in `autor:` for each criterion)
uv run --group eval python -m evals.calibrate compare evals/results/<run>.json
    -> agreement per criterion: mean absolute difference, exact and ±1 agreement, Cohen's weighted kappa
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import yaml

from evals.metrics import CRITERIA

SHEET = Path(__file__).parent / "calibration" / "hoja.yaml"


def _to_five(score: float) -> int:
    """DeepEval's 0-1 score on the 1-5 scale the author uses."""
    return max(1, min(5, round(1 + 4 * score)))


def export(results: Path) -> None:
    rows = json.loads(results.read_text())["results"]["conversations"]
    sheet = {
        "instrucciones": (
            "Puntúa cada respuesta de 1 (muy mal) a 5 (muy bien) en cada criterio, sin mirar las notas del juez. "
            "Los criterios y sus pasos están en evals/metrics.py."
        ),
        "criterios": list(CRITERIA),
        "casos": [
            {
                "id": r["id"],
                "conversacion": [{"usuario": t["message"], "mojo": t["answer"]} for t in r["turns"]],
                "autor": {c: None for c in CRITERIA},
            }
            for r in rows
        ],
    }
    SHEET.parent.mkdir(exist_ok=True)
    SHEET.write_text(yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    print(f"{len(rows)} conversaciones en {SHEET}")


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


def compare(results: Path) -> None:
    judge = {r["id"]: r.get("judge", {}) for r in json.loads(results.read_text())["results"]["conversations"]}
    sheet = yaml.safe_load(SHEET.read_text(encoding="utf-8"))
    print("| Criterio | Casos | Diferencia media | Coinciden | ±1 | Kappa ponderado |")
    print("| --- | --- | --- | --- | --- | --- |")
    for criterion in CRITERIA:
        scored = [c for c in sheet["casos"] if c["autor"].get(criterion) and criterion in judge.get(c["id"], {})]
        pairs = [(c["autor"][criterion], _to_five(judge[c["id"]][criterion]["score"])) for c in scored]
        if not pairs:
            continue
        a, b = [p[0] for p in pairs], [p[1] for p in pairs]
        mad = sum(abs(x - y) for x, y in pairs) / len(pairs)
        exact = sum(x == y for x, y in pairs)
        near = sum(abs(x - y) <= 1 for x, y in pairs)
        print(f"| {criterion} | {len(pairs)} | {mad:.2f} | {exact} | {near} | {_weighted_kappa(a, b):.2f} |")


if __name__ == "__main__":
    {"export": export, "compare": compare}[sys.argv[1]](Path(sys.argv[2]))
