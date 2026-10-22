"""Variants of the agent (Evidencias para la memoria): what each piece adds, on the same conversations.

Each variant is a run of the conversations set with one piece switched off (evals/harness.py: VARIANTS):

    evals/run.sh --sets conversations --variant sin_ficha
    uv run --group eval python -m evals.variants <run.json> <run.json> ...

Only the cases present in every run are compared. The number checker runs in every variant: with it off
it only records, so «cifras sin origen que llegan al usuario» is measured the same way everywhere.
Writes evals/results/<date>-variants.json and a .md with the comparison table.
"""

# ruff: noqa: E501  (this module writes long Markdown lines for the report)
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from evals.baseline import allergen_mentions
from evals.cases import load
from evals.harness import VARIANTS
from evals.run import RESULTS
from mojo_picon.guardrails.number_origin import citations
from mojo_picon.tools.foods import load_foods

CRITERIA = ("adecuacion", "seguridad", "uso_de_guias", "claridad")


def _five(score: float) -> float:
    return 1 + 4 * score


def conversation(row: dict, case: dict, foods) -> dict:
    """Measures of one conversation of a run."""
    turns = row.get("turns", [])
    checks = [c for t in turns for c in t.get("number_checks", [])]
    finals = [t["number_checks"][-1] for t in turns if t.get("number_checks")]
    answers = " ".join(t["answer"] for t in turns)
    allergens = case["esperado"].get("sin_alergenos") or case.get("perfil", {}).get("allergens") or []
    return {
        "id": row["id"],
        "passed": bool(row.get("passed")),
        # what reaches the user: with the checker off, the numbers it would have rejected
        "unsourced_shown": [n for f in finals if f["action"] == "off" for n in f["unsourced"]],
        # what the checker did: a regeneration or sentences removed
        "caught": any(c["action"] in ("regenerate", "drop") for c in checks),
        "dropped": any(c["action"] == "drop" for c in checks),
        "cites": any(citations(t["answer"]) for t in turns),
        "guides": any("search_guides" in t.get("tools", []) for t in turns),
        "allergens": allergen_mentions(answers, allergens, foods) if allergens else None,
        "judge": {k: v["score"] for k, v in (row.get("judge") or {}).items()},
        "tokens": sum(t.get("tokens", {}).get("input", 0) + t.get("tokens", {}).get("output", 0) for t in turns),
        "seconds": sum(t.get("seconds", 0) for t in turns),
    }


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    allergy = [r for r in rows if r["allergens"] is not None]
    judged = [r["judge"] for r in rows if r["judge"]]
    out = {
        "n": n,
        "passed": sum(r["passed"] for r in rows),
        "unsourced_shown": sum(bool(r["unsourced_shown"]) for r in rows),
        "caught": sum(r["caught"] for r in rows),
        "dropped": sum(r["dropped"] for r in rows),
        "cites": sum(r["cites"] for r in rows),
        "guides": sum(r["guides"] for r in rows),
        "allergens": sum(bool(r["allergens"]) for r in allergy),
        "allergy_cases": len(allergy),
        "tokens": statistics.mean(r["tokens"] for r in rows) if rows else 0,
        "latency": statistics.median(r["seconds"] for r in rows) if rows else 0,
    }
    for c in CRITERIA:
        values = [j[c] for j in judged if c in j]
        out[c] = _five(statistics.mean(values)) if values else None
    return out


def table(variants: dict[str, dict], meta: dict) -> str:
    def judge(s, c):
        return f"{s[c]:.1f}" if s[c] is not None else "—"

    n = next(iter(variants.values()))["n"]
    lines = [
        f"# Variantes del agente · {meta['started']}", "",
        f"Mismos {n} casos de conversación en todas las variantes, mismo modelo ({meta['model']}) y mismo juez "
        f"({meta['judge'] or 'sin juez'}). Cada variante apaga una pieza; el comprobador de cifras mide en todas.", "",
        "| Variante | Pasan las comprobaciones | Cifras sin origen que llegan al usuario | El comprobador corrige | Cita una fuente | Usa search_guides | Propone alérgenos | Tokens por conversación | Latencia mediana |",
        "|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for name, s in variants.items():
        tokens = f"{s['tokens']:,.0f}".replace(",", ".")
        label = f"**{VARIANTS[name].description}**" if name == "completo" else VARIANTS[name].description
        lines.append(
            f"| {label} | {s['passed']}/{s['n']} | {s['unsourced_shown']}/{s['n']} | {s['caught']}/{s['n']} "
            f"({s['dropped']} con frases eliminadas) | {s['cites']}/{s['n']} | {s['guides']}/{s['n']} | "
            f"{s['allergens']} de {s['allergy_cases']} | {tokens} | {s['latency']:.1f} s |"
        )  # fmt: skip
    lines += [
        "",
        "## Juez (1-5)",
        "",
        "| Variante | " + " | ".join(CRITERIA) + " |",
        "|---" * (len(CRITERIA) + 1) + "|",
    ]
    for name, s in variants.items():
        lines.append(f"| {VARIANTS[name].description} | " + " | ".join(judge(s, c) for c in CRITERIA) + " |")
    lines += ["", "Ejecuciones:", ""] + [f"- {name}: `{path}`" for name, path in meta["runs"].items()]
    if meta.get("dropped_cases"):
        lines += [
            "",
            f"Casos que no están en todas las ejecuciones (no comparados): {', '.join(meta['dropped_cases'])}",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", type=Path, nargs="+", help="runs of the conversations set, one per variant")
    args = parser.parse_args()
    loaded = {}
    for path in args.runs:
        data = json.loads(path.read_text())
        variant = data["meta"].get("variant", "completo")
        if variant in loaded:
            raise SystemExit(f"two runs of the variant {variant}: {loaded[variant][0]} and {path}")
        loaded[variant] = (path, data)
    order = [v for v in VARIANTS if v in loaded]
    by_variant = {v: {r["id"]: r for r in loaded[v][1]["results"]["conversations"]} for v in order}
    common = set.intersection(*(set(rows) for rows in by_variant.values()))
    every = set.union(*(set(rows) for rows in by_variant.values()))
    cases = {c["id"]: c for c in load("conversations")}
    foods = load_foods()
    per_case = {v: [conversation(by_variant[v][i], cases[i], foods) for i in sorted(common)] for v in order}
    first = loaded[order[0]][1]["meta"]
    meta = {"started": datetime.now().strftime("%Y-%m-%d %H:%M"), "model": first["model"], "judge": first["judge"],
            "runs": {v: str(loaded[v][0]) for v in order}, "dropped_cases": sorted(every - common)}  # fmt: skip
    variants = {v: summary(rows) for v, rows in per_case.items()}
    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-variants"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": variants, "cases": per_case}, ensure_ascii=False, indent=1)
    )
    stem.with_suffix(".md").write_text(table(variants, meta))
    print(table(variants, meta))


if __name__ == "__main__":
    main()
