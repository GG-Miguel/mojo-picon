"""Full evaluation: every set, its code checks, the judge on conversations; JSON + Markdown report.

    set -a; . ./.env; set +a
    DEEPEVAL_TELEMETRY_OPT_OUT=YES uv run --group eval python -m evals.run [--sets safety,attacks] [--repeat 3]
        [--partition desarrollo|prueba|all] [--no-judge]

Real Gemini (EU endpoint), real Qdrant, an in-memory store per case. Results go to evals/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from evals import checks
from evals.cases import load, partition
from evals.harness import Harness, Run
from evals.metrics import RUBRIC_VERSION
from mojo_picon.agents.planner import build_planner
from mojo_picon.domain import Allergen, MacroTargets
from mojo_picon.rag.index import guide_index_from_settings

RESULTS = Path(__file__).parent / "results"
SETS = ["numbers", "rag", "safety", "attacks", "planner", "conversations"]
CONCURRENCY = 4


INFRA_RETRIES = 2  # a case whose turn failed (e.g. Vertex AI 429) is run again after a pause
INFRA_PAUSE_S = 45


def _infra_error(result: dict) -> bool:
    """The turn broke (the API answered with an error event): not a verdict on the agent."""
    return any(t.get("errors") for t in result.get("turns", []))


async def bounded(items, fn, limit=CONCURRENCY):
    semaphore = asyncio.Semaphore(limit)

    async def one(item):
        async with semaphore:
            try:
                result = await fn(item)
                for _ in range(INFRA_RETRIES):
                    if not _infra_error(result):
                        break
                    await asyncio.sleep(INFRA_PAUSE_S)
                    result = await fn(item)
                if _infra_error(result):
                    result = {**result, "passed": None, "infra_error": True}
                return result
            except Exception as e:  # one broken case must not stop the run; it is reported as failed
                return {"id": item[0]["id"] if isinstance(item, tuple) else item["id"], "passed": False,
                        "error": f"{type(e).__name__}: {e}"[:300]}  # fmt: skip

    return await asyncio.gather(*(one(i) for i in items))


def _verdict(results: list[tuple[str, tuple[bool, str]]]) -> dict:
    return {
        "passed": all(ok for _, (ok, _) in results),
        "checks": {name: {"ok": ok, "detail": d} for name, (ok, d) in results},
    }


def _summary(run: Run) -> dict:
    return {
        "turns": [{"message": t.message, "answer": t.answer, "guard": t.guard_level, "tools": t.tools,
                   "seconds": round(t.seconds, 1), "regenerations": t.regenerations, "errors": t.errors,
                   "sources": t.sources} for t in run.turns],
        "entries": [e.model_dump(mode="json") for e in run.entries],
    }  # fmt: skip


# --- sets ---------------------------------------------------------------------------------


async def eval_numbers(cases, **_):
    out = []
    for case in cases:
        flagged, expected = checks.number_case(case)
        out.append({"id": case["id"], "passed": flagged == expected, "flagged": flagged, "expected": expected})
    return out


async def eval_rag(cases, h: Harness, **_):
    index = guide_index_from_settings(h.settings)

    async def one(case):
        hits = await index.search(case["pregunta"], k=5)
        tags = [x.tag for x in hits]
        rank = next((i + 1 for i, t in enumerate(tags) if any(t.startswith(s) for s in case["fuente"])), None)
        return {"id": case["id"], "passed": rank is not None and rank <= 3, "rank": rank, "top5": tags}

    return await bounded(cases, one)


async def eval_safety(cases, h: Harness, repeat=1, **_):
    async def one(item):
        case, rep = item
        run = await h.chat(case, [case["mensaje"]])
        verdict = _verdict([("guardian", checks.guardian(run, case["esperado"]["guardian"]))])
        return {"id": case["id"], "rep": rep, "twin": bool(case.get("gemelo_de")), **verdict, **_summary(run)}

    return await bounded([(c, r) for c in cases for r in range(repeat)], one)


async def eval_attacks(cases, h: Harness, repeat=1, **_):
    async def one(item):
        case, rep = item
        run = await h.chat(case, [case["mensaje"]], photo_text=case.get("foto_texto"))
        results = []
        for check in case["checks"]:
            name, arg = next(iter(check.items())) if isinstance(check, dict) else (check, None)
            results.append((name, _attack_check(name, arg, run, h)))
        out = {"id": case["id"], "rep": rep, **_verdict(results), **_summary(run)}
        if case.get("foto_texto") and not _vision_saw_food(run):
            out.update(
                passed=None, inconclusive="la visión no vio comida: la instrucción de la foto no llegó a probarse"
            )
        return out

    return await bounded([(c, r) for c in cases for r in range(repeat)], one)


def _vision_saw_food(run: Run) -> bool:
    steps = [
        e for e in run.turns[0].events if e["type"] == "step" and e.get("id") == "vision" and e["status"] == "done"
    ]
    return bool(steps) and steps[-1].get("detail") != "no veo comida"


def _attack_check(name: str, arg, run: Run, h: Harness) -> tuple[bool, str]:
    if name == "guardian_derivar":
        return checks.guardian(run, "derivar")
    if name == "no_leak":
        return checks.no_leak(run)
    if name == "no_other_user":
        return checks.no_other_user(run, h.foods)
    if name == "no_entry_over_g":
        return checks.no_entry_over(run, arg)
    if name == "no_food_logged":
        return checks.no_food_logged(run, arg)
    if name == "no_figure":
        return checks.no_figure(run)
    if name == "photo_no_follow":
        return checks.photo_no_follow(run, arg)
    raise ValueError(f"unknown check {name}")


async def eval_planner(cases, h: Harness, repeat=1, **_):
    planner = build_planner(h.models, h.foods)

    async def one(item):
        case, rep = item
        start = time.time()
        result = await planner.ainvoke({
            "meals": case["comidas"], "preferences": case.get("preferencias", ""),
            "remaining": MacroTargets(**case["queda"]),
            "allergens": [Allergen(a) for a in case.get("alergenos", [])],
        })  # fmt: skip
        plan = result.get("plan")
        ids = [i.food_id for i in plan.items] if plan else []
        meals = [
            {"comida": m.name, "alimentos": [[i.food_id, i.grams] for i in m.items]}
            for m in (plan.meals if plan else [])
        ]
        totals = {k: 0.0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
        for item in plan.items if plan else []:
            n = h.foods[item.food_id].nutrients_for(item.grams)
            for k in totals:
                totals[k] += getattr(n, k)
        allergens = [f for f in ids if h.foods[f].allergens & set(case.get("alergenos", []))]
        return {"id": case["id"], "rep": rep, "passed": bool(result.get("passed")) and not allergens,
                "attempts": result.get("attempts"), "issues": result.get("issues", []), "foods": ids, "meals": meals,
                "totals": {k: round(v) for k, v in totals.items()},
                "allergens_found": allergens, "seconds": round(time.time() - start, 1)}  # fmt: skip

    return await bounded([(c, r) for c in cases for r in range(repeat)], one)


async def eval_conversations(cases, h: Harness, repeat=1, judge=None, **_):
    async def one(item):
        case, rep = item
        run = await h.chat(case, case["turnos"], simulated=case.get("usuario_simulado"))
        exp = case["esperado"]
        results = [("trayectoria", checks.trajectory(run)), ("sin_disculpas", checks.no_stray_apology(run))]
        if "guardian" in exp:
            results.append(("guardian", checks.guardian(run, exp["guardian"])))
        if exp.get("herramientas"):
            results.append(("herramientas", checks.tools(run, exp["herramientas"])))
        if exp.get("sin_herramientas"):
            results.append(("sin_herramientas", checks.no_tools(run, exp["sin_herramientas"])))
        if exp.get("sin_alergenos"):
            results.append(("sin_alergenos", checks.no_allergens(run, h.foods, exp["sin_alergenos"])))
        if exp.get("plan_sin_categorias"):
            results.append(("plan_sin_categorias", checks.no_categories(run, h.foods, exp["plan_sin_categorias"])))
        if exp.get("menciona_profesional"):
            results.append(("menciona_profesional", checks.mentions_professional(run)))
        if exp.get("pregunta_antes_de_registrar"):
            results.append(("pregunta_antes_de_registrar", checks.asks_before_logging(run)))
        if exp.get("sin_animar_alcohol"):
            results.append(("sin_animar_alcohol", checks.no_endorses_alcohol(run)))
        if exp.get("cita_fuente"):
            results.append(("cita_fuente", checks.cites_source(run)))
        out = {"id": case["id"], "rep": rep, **_verdict(results), **_summary(run)}
        if judge is not None:
            from evals.metrics import score

            context = [
                f"Perfil: {case.get('perfil')}",
                f"Registrado hoy antes de la conversación: {case.get('hoy', {})}",
                f"Nivel del guardián: {run.turns[0].guard_level}",
            ]
            user_input = run.turns[0].message
            if len(run.turns) == 1:
                answer = run.turns[0].answer
            else:  # a dialogue, so the judge sees what was asked and answered in order
                answer = "\n\n".join(f"Usuario: {t.message}\nMojo: {t.answer}" for t in run.turns)
            out["judge"] = await score(judge, user_input, answer, context)
        return out

    return await bounded([(c, r) for c in cases for r in range(repeat)], one, limit=2)


# --- report -------------------------------------------------------------------------------


def report(results: dict, meta: dict) -> str:
    lines = [f"# Evaluación · {meta['started']}", "",
             f"Partición: **{meta['partition']}** · repeticiones: {meta['repeat']} · modelo: {meta['model']} · "
             f"juez: {meta['judge'] or 'sin juez'} · duración: {meta['seconds'] / 60:.1f} min", ""]  # fmt: skip
    for name, all_rows in results.items():
        infra = [r for r in all_rows if r.get("infra_error")]
        unproven = [r for r in all_rows if r.get("inconclusive")]
        rows = [r for r in all_rows if not r.get("infra_error") and not r.get("inconclusive")]
        passed = sum(bool(r.get("passed")) for r in rows)
        lines += [f"## {name}", "", f"**{passed} de {len(rows)}** ({100 * passed / max(len(rows), 1):.0f} %)", ""]
        if infra:
            ids = ", ".join(r["id"] for r in infra)
            lines.append(f"- Sin veredicto por error de infraestructura (p. ej. 429 de Vertex AI): {ids}")
        for r in unproven:
            lines.append(f"- No concluyente: {r['id']} ({r['inconclusive']})")
        if name == "safety":
            risky = [r for r in rows if not r.get("twin")]
            twins = [r for r in rows if r.get("twin")]
            lines.append(f"- Peticiones de riesgo derivadas: {sum(r['passed'] for r in risky)} de {len(risky)}")
            lines.append(
                f"- Casos legítimos bloqueados por error: {sum(not r['passed'] for r in twins)} de {len(twins)}"
            )
        if name == "numbers":
            tp = sum(r["flagged"] and r["expected"] for r in rows)
            fn = sum(not r["flagged"] and r["expected"] for r in rows)
            fp = sum(r["flagged"] and not r["expected"] for r in rows)
            neg = sum(not r["expected"] for r in rows)
            lines.append(f"- Cifras sin origen detectadas: {tp} de {tp + fn}")
            lines.append(f"- Respuestas correctas rechazadas por error: {fp} de {neg}")
        if name == "rag":
            for k in (1, 3, 5):
                hit = sum(r.get("rank") is not None and r["rank"] <= k for r in rows)
                lines.append(f"- recall@{k}: {hit} de {len(rows)}")
        if name == "planner":
            ok = [r for r in rows if "attempts" in r]
            first = sum(r["passed"] and r["attempts"] == 1 for r in ok)
            later = sum(r["passed"] and r["attempts"] > 1 for r in ok)
            lines.append(
                f"- Al primer intento: {first} · tras corregir: {later} · no converge: {len(ok) - first - later}"
            )
            if ok:
                lines.append(f"- Tiempo mediano: {statistics.median(r['seconds'] for r in ok):.0f} s")
        if name == "conversations" and any("judge" in r for r in rows):
            for crit in ("adecuacion", "seguridad", "uso_de_guias", "claridad"):
                values = [r["judge"][crit]["score"] for r in rows if "judge" in r]
                lines.append(
                    f"- {crit}: media {statistics.mean(values):.2f} (≈ {1 + 4 * statistics.mean(values):.1f} sobre 5)"
                )
        failed = [r for r in rows if not r.get("passed")]
        if failed:
            lines += ["", "| Caso | Fallo |", "| --- | --- |"]
            for r in failed:
                lines.append(f"| {r['id']} | {_why(r)[:200].replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)


def _why(r: dict) -> str:
    if r.get("error"):
        return r["error"]
    failed = [f"{k}: {v['detail']}" for k, v in r.get("checks", {}).items() if not v["ok"]]
    if failed:
        return "; ".join(failed)
    return json.dumps({k: r[k] for k in ("flagged", "expected", "rank", "issues") if k in r}, ensure_ascii=False)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sets", default=",".join(SETS))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--partition", default="all", choices=["desarrollo", "prueba", "all"])
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--ids", default="", help="only these case ids, comma-separated (quick checks)")
    args = parser.parse_args()

    h = Harness()
    judge = None
    if not args.no_judge and "conversations" in args.sets:
        from evals.judge import GroqJudge
        from evals.metrics import rubric

        judge_model = GroqJudge()
        judge = rubric(judge_model)
    started = datetime.now()
    start = time.time()
    results = {}
    for name in args.sets.split(","):
        cases = [c for c in load(name) if args.partition == "all" or partition(c) == args.partition]
        if args.ids:
            cases = [c for c in cases if c["id"] in args.ids.split(",")]
        print(f"{name}: {len(cases)} casos…", flush=True)
        fn = globals()[f"eval_{name}"]
        results[name] = await fn(cases, h=h, repeat=args.repeat, judge=judge)
    judge_name = f"openai/gpt-oss-120b (Groq), rúbrica {RUBRIC_VERSION}" if judge else None
    meta = {"started": started.strftime("%Y-%m-%d %H:%M"), "partition": args.partition, "repeat": args.repeat,
            "model": h.settings.gemini_model, "judge": judge_name, "seconds": time.time() - start}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"{started.strftime('%Y%m%d-%H%M%S')}-{args.partition}-{'+'.join(results)}"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1, default=str)
    )
    stem.with_suffix(".md").write_text(report(results, meta))
    print(report(results, meta))


if __name__ == "__main__":
    asyncio.run(main())
