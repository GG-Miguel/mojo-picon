"""Models per role (ADR-04): the same sets with one role on another model, to choose with quality, cost and latency.

Each run is a normal evaluation with MODEL_<ROLE> set (evals/models.sh runs them all):

    MODEL_GUARDIAN=gemini-3.5-flash-lite evals/run.sh --sets safety,attacks --no-judge --repeat 3
    uv run --group eval python -m evals.models <run.json> <run.json> ...

The run with every role on GEMINI_MODEL is the reference. Cases without a verdict (an infrastructure error
such as a 429, or inconclusive) are counted apart and left out of the rates. Costs: evals/prices.py.
Writes evals/results/<date>-models.json and a .md with one table per set.
"""

# ruff: noqa: E501  (this module writes long Markdown lines for the report)
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from evals.prices import PRICES, PRICES_2027, cost
from mojo_picon.config import ROLES

# Not imported from evals.run: that pulls DeepEval, which the unit tests in the CI do not install.
RESULTS = Path(__file__).parent / "results"

SETS = ("safety", "attacks", "planner", "conversations")
CRITERIA = ("adecuacion", "seguridad", "uso_de_guias", "claridad")


def changed(meta: dict) -> dict[str, str]:
    """The roles of a run that do not use GEMINI_MODEL."""
    return {role: m for role, m in meta.get("models", {}).items() if m != meta["model"]}


def label(meta: dict) -> str:
    roles = changed(meta)
    return ", ".join(f"{role}: {m}" for role, m in roles.items()) if roles else f"referencia ({meta['model']})"


def _usage(row: dict) -> dict[str, dict[str, int]]:
    """{role or model: {input, output}} of one case, every turn added."""
    parts = [row.get("tokens_by_model", {})] + [t.get("tokens_by_model", {}) for t in row.get("turns", [])]
    out: dict[str, dict[str, int]] = {}
    for part in parts:
        for key, tokens in part.items():
            total = out.setdefault(key, {"input": 0, "output": 0})
            for k in total:
                total[k] += tokens.get(k, 0)
    return out


def _model(key: str, meta: dict) -> str:
    """Through the gateway the key is the role; in direct mode, the model."""
    return meta.get("models", {}).get(key, meta["model"]) if key in ROLES else key


def _cost(usage: dict, meta: dict, prices: dict, only: set[str] | None = None) -> float | None:
    costs = [cost(t, _model(k, meta), prices) for k, t in usage.items() if only is None or k in only]
    return None if any(c is None for c in costs) else sum(costs)


def _seconds(row: dict) -> float:
    return row.get("seconds") or sum(t.get("seconds", 0) for t in row.get("turns", []))


def summary(rows: list[dict], meta: dict, name: str) -> dict:
    infra = [r for r in rows if r.get("infra_error") or r.get("error")]
    unproven = [r for r in rows if r.get("inconclusive")]
    scored = [r for r in rows if r not in infra and r not in unproven]
    usages = [_usage(r) for r in scored]
    roles = set(changed(meta))
    out = {
        "n": len(scored), "infra": len(infra), "inconclusive": len(unproven),
        "passed": sum(bool(r.get("passed")) for r in scored),
        "tokens": statistics.mean(sum(t["input"] + t["output"] for t in u.values()) for u in usages) if usages else 0,
        "latency": statistics.median(_seconds(r) for r in scored) if scored else 0,
    }  # fmt: skip
    for key, prices in (("cost", PRICES), ("cost_2027", PRICES_2027)):
        costs = [_cost(u, meta, prices) for u in usages]
        out[key] = statistics.mean(costs) if costs and None not in costs else None
    role_costs = [_cost(u, meta, PRICES, roles) for u in usages] if roles else []
    out["role_cost"] = statistics.mean(role_costs) if role_costs and None not in role_costs else None
    if name == "safety":
        risky, twins = [r for r in scored if not r.get("twin")], [r for r in scored if r.get("twin")]
        out["referred"] = f"{sum(bool(r['passed']) for r in risky)}/{len(risky)}"
        out["over_blocked"] = f"{sum(not r['passed'] for r in twins)}/{len(twins)}"
    if name == "planner":
        attempts = [r.get("attempts") for r in scored if r.get("passed")]
        out["first_attempt"] = sum(a == 1 for a in attempts)
        out["attempts"] = statistics.mean(attempts) if attempts else None
    if name == "conversations":
        for c in CRITERIA:
            values = [r["judge"][c]["score"] for r in scored if r.get("judge") and c in r["judge"]]
            out[c] = 1 + 4 * statistics.mean(values) if values else None
    return out


def _money(value: float | None) -> str:
    return f"{value * 1000:.2f}" if value is not None else "—"


def table(runs: list[tuple[str, dict, dict]]) -> str:
    lines = [f"# Modelos por papel · {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
             "Cada fila cambia el modelo de un papel; el resto sigue en el de referencia. Los casos con error de "
             "infraestructura (p. ej. un 429) o no concluyentes no cuentan en las tasas. Coste en milésimas de dólar "
             "(m$) por caso, con los precios de `evals/prices.py` (sin descontar la caché: es un máximo).", ""]  # fmt: skip
    for name in SETS:
        present = [(lab, s[name], meta) for lab, s, meta in runs if name in s]
        if not present:
            continue
        extra = {"safety": ["Riesgos derivados", "Bloqueos de más"], "planner": ["Al primer intento", "Intentos medios"],
                 "conversations": [c for c in CRITERIA]}.get(name, [])  # fmt: skip
        lines += [f"## {name}", "",
                  "| Configuración | Pasan | Sin veredicto | " + " | ".join(extra) + (" | " if extra else "")
                  + "Coste por caso (m$) | Del papel cambiado (m$) | Desde 2027 (m$) | Tokens por caso | Latencia mediana |",
                  "|---" * (8 + len(extra)) + "|"]  # fmt: skip
        for lab, s, _ in present:
            if name == "safety":
                cells = [s["referred"], s["over_blocked"]]
            elif name == "planner":
                cells = [f"{s['first_attempt']}/{s['n']}", f"{s['attempts']:.1f}" if s["attempts"] else "—"]
            elif name == "conversations":
                cells = [f"{s[c]:.1f}" if s[c] is not None else "—" for c in CRITERIA]
            else:
                cells = []
            tokens = f"{s['tokens']:,.0f}".replace(",", ".")
            lines.append(
                f"| {lab} | {s['passed']}/{s['n']} | {s['infra'] + s['inconclusive']} | "
                + "".join(f"{c} | " for c in cells)
                + f"{_money(s['cost'])} | {_money(s['role_cost'])} | {_money(s['cost_2027'])} | {tokens} | {s['latency']:.1f} s |"
            )
        lines.append("")
    lines += ["Ejecuciones:", ""] + [f"- {lab}: `{meta['path']}`" for lab, _, meta in runs]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", type=Path, nargs="+", help="evaluation runs, one per configuration of models")
    args = parser.parse_args()
    runs = []
    for path in args.runs:
        data = json.loads(path.read_text())
        meta = {**data["meta"], "path": str(path)}
        sets = {name: summary(rows, meta, name) for name, rows in data["results"].items() if name in SETS}
        runs.append((label(meta), sets, meta))
    runs.sort(key=lambda r: (bool(changed(r[2])), r[0]))  # the reference first
    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-models"
    stem.with_suffix(".json").write_text(
        json.dumps([{"label": lab, "meta": meta, "summary": s} for lab, s, meta in runs], ensure_ascii=False, indent=1)
    )
    stem.with_suffix(".md").write_text(table(runs))
    print(table(runs))


if __name__ == "__main__":
    main()
