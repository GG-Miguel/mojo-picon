"""Package photos: the vision extractor on real packages (ingredients list and nutrition table).

Each package of evals/cases/packages.yaml has two photos in evals/fixtures/packages: its ingredients
list and its nutrition table. The extractor runs on each, as in the app (same resize, same prompt), and
the code compares what it read with what is printed:

- allergens missed (the serious error: an allergic user is not warned), from the ingredients photo,
  counting what the model names plus what the code finds in the list (vision/allergens.py);
- false alarms (an allergen that the package does not declare), which cost a question, not a risk;
- the kcal per 100 g or 100 ml read from the nutrition table, within 2 % of a printed value.

    evals/packages.sh [--repeat 2]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from evals.cases import load
from mojo_picon.config import Settings
from mojo_picon.domain import Allergen
from mojo_picon.llm import model_provider
from mojo_picon.vision.extractor import extract, package_allergens, prepare_image

FIXTURES = Path(__file__).parent / "fixtures" / "packages"
RESULTS = Path(__file__).parent / "results"
KCAL_TOLERANCE = 0.02


async def one(models, case: dict) -> dict:
    code = case["codigo"]
    ingredients = await extract(models, prepare_image((FIXTURES / f"{code}_ingredients.jpg").read_bytes()))
    table = await extract(models, prepare_image((FIXTURES / f"{code}_nutrition.jpg").read_bytes()))
    contains, traces = package_allergens(ingredients)
    seen = contains | traces
    expected = {Allergen(a) for a in case.get("contiene", [])}
    expected_traces = {Allergen(a) for a in case.get("puede_contener", [])}
    allowed = expected | expected_traces | {Allergen(a) for a in case.get("admite", [])}
    kcal = table.label.kcal if table.label else None
    kcal_ok = kcal is not None and any(abs(kcal - k) <= KCAL_TOLERANCE * k for k in case["kcal"])
    return {
        "codigo": code,
        "producto": case["producto"],
        "ingredientes_leidos": len(ingredients.ingredients),
        "faltan": sorted(expected - contains) + sorted(expected_traces - seen),
        "falsas_alarmas": sorted(seen - allowed),
        "kcal": kcal,
        "kcal_ok": kcal_ok,
    }


def report(rows: list[dict], repeat: int) -> str:
    n = len(rows)
    missed = sum(bool(r["faltan"]) for r in rows)
    alarms = sum(bool(r["falsas_alarmas"]) for r in rows)
    kcal = sum(r["kcal_ok"] for r in rows)
    lines = [
        f"# Envases reales · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"{n // repeat} envases × {repeat} repeticiones. Alérgenos que se escapan en {missed} de {n} lecturas; "
        f"falsas alarmas en {alarms} de {n}; kcal bien leídas en {kcal} de {n}.",
        "",
        "| Envase | Ingredientes leídos | Alérgenos que faltan | Falsas alarmas | kcal leídas |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        kcal_text = "no se leyó la tabla" if r["kcal"] is None else f"{r['kcal']:g}" + ("" if r["kcal_ok"] else " ✗")
        lines.append(
            f"| {r['producto']} | {r['ingredientes_leidos']} | {', '.join(r['faltan']) or '—'} | "
            f"{', '.join(r['falsas_alarmas']) or '—'} | {kcal_text} |"
        )
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    models = model_provider(Settings.from_env())
    cases = load("packages")
    rows = [await one(models, case) for _ in range(args.repeat) for case in cases]
    text = report(rows, args.repeat)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-packages.md").write_text(text)
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
