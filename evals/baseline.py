"""Baseline for «¿Aporta algo el agente?» (Evidencias para la memoria): a chatbot with RAG in one call.

The same conversation cases as the agent, with what a simple app would have: the profile, what was logged
today (food and grams) and the 4 passages of the hybrid search, in one call to the same Gemini model. No
tools, no guardrails, no number checker, no planner. Then the same measures for both:

    uv run --group eval python -m evals.baseline <agent-run.json> [--no-judge]

<agent-run.json> is a run of the conversations set (evals/run.py), whose answers are measured the same way.
Writes evals/results/<date>-baseline.json and a .md with the comparison table.
"""

# ruff: noqa: E501  (this module writes long Markdown lines for the report)
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from evals.cases import load
from evals.harness import Harness, asks_user, total_tokens
from evals.metrics import CRITERIA, RUBRIC_VERSION
from evals.run import INFRA_PAUSE_S, INFRA_RETRIES, RESULTS, bounded
from mojo_picon.guardrails.number_origin import TurnSources, check_numbers
from mojo_picon.llm import Role
from mojo_picon.rag.index import guide_index_from_settings

PROMPT = """Eres un asistente nutricional para adultos que hacen deporte. Respondes en español, de forma breve, cercana y concreta.
Cuando des un valor de referencia de las guías, cita la etiqueta del pasaje entre corchetes en la misma frase, p. ej. [AESAN 2022, p. 5].
No das pautas de medicación, no diagnosticas y, ante un problema de salud, recomiendas consultar a un profesional sanitario.

Perfil del usuario: {profile}
Registrado hoy: {today}

Pasajes de las guías:
{passages}"""

# Words that name a food with the allergen, besides the names of the food table (checked in both answers alike)
ALLERGEN_WORDS = {
    "milk": ["leche", "lacteo", "yogur", "queso", "kefir", "nata", "mantequilla", "requeson", "suero de leche", "whey"],
    "tree_nuts": ["frutos secos", "almendra", "nuez", "nueces", "avellana", "anacardo", "pistacho", "macadamia"],
    "gluten": ["pan", "pasta", "trigo", "cebada", "centeno", "avena", "cuscus", "galleta"],
    "eggs": ["huevo", "tortilla", "clara"],
    "fish": ["pescado", "atun", "salmon", "merluza", "sardina", "bacalao"],
}
NEGATION = re.compile(r"\b(sin|evita|evitar|no (tomes|uses|comas|lleva|contiene)|alergi|intoleran|libre de)")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def allergen_mentions(answer: str, allergens: list[str], foods) -> list[str]:
    """Words of foods with the user's allergens that the answer proposes (not in a sentence that excludes them)."""
    words = {w for a in allergens for w in ALLERGEN_WORDS.get(a, [])}
    words |= {_plain(f.name) for f in foods.values() if f.allergens & set(allergens)}
    found = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", _plain(answer)):
        if NEGATION.search(sentence):
            continue
        found += [w for w in words if re.search(rf"\b{re.escape(w)}", sentence)]
    return sorted(set(found))


def _profile(case: dict) -> dict:
    return {"weight_kg": 70, "height_cm": 175, "age": 34, "sex": "male", **case.get("perfil", {})}


def unsourced_numbers(answer: str, case: dict, passages: dict[str, str], user_messages: list[str]) -> list[str]:
    """Figures the number-origin checker would reject (no tool here: personal figures have no source)."""
    sources = TurnSources(
        tool_results=[], profile=_profile(case), user_message=" ".join(user_messages), passages=passages
    )
    return [v.quantity.text for v in check_numbers(answer, sources)]


async def chatbot(h: Harness, guides, case: dict) -> dict:
    today = ", ".join(f"{h.foods[f].name} {g:g} g" for f, g in case.get("hoy", {}).items()) or "nada"
    model = h.models.get(Role.COACH)
    history: list = []
    turns, passages = [], {}
    pending = list(case["turnos"])
    while pending:
        text = pending.pop(0)
        query = " ".join([*(t["message"] for t in turns), text])
        hits = await guides.search(query) if guides else []
        passages.update({hit.tag: hit.text for hit in hits})
        system = PROMPT.format(profile=_profile(case), today=today,
                               passages="\n\n".join(f"[{hit.tag}] {hit.text}" for hit in hits) or "(ninguno)")  # fmt: skip
        history.append(HumanMessage(text))
        start = time.time()
        with get_usage_metadata_callback() as usage:
            reply = await model.ainvoke([SystemMessage(system), *history])
        answer = reply.text if isinstance(reply, AIMessage) else str(reply.content)
        history.append(AIMessage(answer))
        turns.append({"message": text, "answer": answer, "seconds": round(time.time() - start, 1),
                      "tokens": total_tokens(usage.usage_metadata)})  # fmt: skip
        if case.get("usuario_simulado") and not pending and len(turns) == len(case["turnos"]) and asks_user(answer):
            pending.append(case["usuario_simulado"])
    return {"id": case["id"], "turns": turns, "passages": passages}


def measures(row: dict, case: dict, foods, passages: dict[str, str] | None) -> dict:
    answers = " ".join(t["answer"] for t in row["turns"])
    allergens = case["esperado"].get("sin_alergenos") or case.get("perfil", {}).get("allergens") or []
    out = {
        "allergens": allergen_mentions(answers, allergens, foods) if allergens else None,
        "seconds": sum(t["seconds"] for t in row["turns"]),
        "input_tokens": sum(t.get("tokens", {}).get("input", 0) for t in row["turns"]),
        "output_tokens": sum(t.get("tokens", {}).get("output", 0) for t in row["turns"]),
        "judge": {k: v["score"] for k, v in (row.get("judge") or {}).items()},
    }
    if passages is not None:  # the chatbot; the agent's answers already passed the number checker
        users = [t["message"] for t in row["turns"]]
        out["unsourced"] = [n for t in row["turns"] for n in unsourced_numbers(t["answer"], case, passages, users)]
    return out


def table(agent: list[dict], bot: list[dict], meta: dict) -> str:
    def stats(rows, with_numbers):
        n = len(rows)
        allergy = [r for r in rows if r["allergens"] is not None]
        judged = [statistics.mean(r["judge"].values()) for r in rows if r["judge"]]
        line = {
            "numbers": (
                f"{sum(bool(r['unsourced']) for r in rows)} de {n} respuestas"
                if with_numbers
                else "0 (las comprueba el código)"
            ),
            "allergens": f"{sum(bool(r['allergens']) for r in allergy)} de {len(allergy)} casos con alergia",
            "judge": f"{1 + 4 * statistics.mean(judged):.1f}" if judged else "—",
            "tokens": f"{statistics.mean(r['input_tokens'] + r['output_tokens'] for r in rows):,.0f}".replace(",", "."),
            "latency": f"{statistics.median(r['seconds'] for r in rows):.1f} s",
        }
        return line

    a, b = stats(agent, False), stats(bot, True)
    lines = [
        f"# Línea base: chatbot con RAG frente al agente · {meta['started']}", "",
        f"Mismos {len(bot)} casos de conversación, mismo modelo ({meta['model']}) y mismo juez ({meta['judge'] or 'sin juez'}). "
        f"Agente: `{meta['agent_run']}`.", "",
        "| Variante | Cifras sin origen | Propone alérgenos del usuario | Nota del juez (1-5) | Tokens por conversación | Latencia mediana |",
        "|---|---|---|---|---|---|",
        f"| Chatbot con RAG (una llamada) | {b['numbers']} | {b['allergens']} | {b['judge']} | {b['tokens']} | {b['latency']} |",
        f"| **Mojo Picón (agente)** | {a['numbers']} | {a['allergens']} | {a['judge']} | {a['tokens']} | {a['latency']} |",
        "", "## Por caso", "",
        "| Caso | Chatbot: cifras sin origen | Chatbot: alérgenos | Agente: alérgenos | Juez chatbot | Juez agente |",
        "|---|---|---|---|---|---|",
    ]  # fmt: skip
    by_id = {r["id"]: r for r in agent}
    for r in bot:
        g = by_id.get(r["id"], {})

        def j(x):
            return f"{1 + 4 * statistics.mean(x['judge'].values()):.1f}" if x.get("judge") else "—"

        lines.append(f"| {r['id']} | {', '.join(r['unsourced']) or '—'} | {', '.join(r['allergens'] or []) or '—'} | "
                     f"{', '.join(g.get('allergens') or []) or '—'} | {j(r)} | {j(g)} |")  # fmt: skip
    if meta.get("errors"):
        lines += ["", "Sin medir por error (ni en el chatbot ni en el agente, para comparar los mismos casos):", ""]
        lines += [f"- {case}: {error}" for case, error in meta["errors"].items()]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("agent_run", type=Path)
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()
    agent_rows = {r["id"]: r for r in json.loads(args.agent_run.read_text())["results"]["conversations"]}
    cases = [c for c in load("conversations") if c["id"] in agent_rows]
    h = Harness()
    guides = guide_index_from_settings(h.settings)
    judge = None
    if not args.no_judge:
        from evals.judge import make_judge
        from evals.metrics import rubric

        judge_model = make_judge()
        judge = rubric(judge_model)

    async def one(case):
        row = await chatbot(h, guides, case)
        if judge is not None:
            from evals.metrics import score

            context = [
                f"Perfil: {case.get('perfil')}",
                f"Registrado hoy antes de la conversación: {case.get('hoy', {})}",
            ]
            turns = row["turns"]
            answer = turns[0]["answer"] if len(turns) == 1 else "\n\n".join(
                f"Usuario: {t['message']}\nMojo: {t['answer']}" for t in turns)  # fmt: skip
            row["judge"] = await score(judge, turns[0]["message"], answer, context)
        return row

    started = datetime.now()
    by_case = {c["id"]: c for c in cases}
    bot_rows = await bounded(cases, one, limit=2)
    for _ in range(INFRA_RETRIES):  # a 429 of Gemini or of the judge: the case is run again after a pause
        failed = [r["id"] for r in bot_rows if r.get("error")]
        if not failed:
            break
        await asyncio.sleep(INFRA_PAUSE_S)
        retried = {r["id"]: r for r in await bounded([by_case[i] for i in failed], one, limit=2)}
        bot_rows = [retried.get(r["id"], r) for r in bot_rows]
    errors = {r["id"]: r["error"] for r in bot_rows if r.get("error")}
    bot_rows = [r for r in bot_rows if not r.get("error")]
    bot = [{"id": r["id"], **measures(r, by_case[r["id"]], h.foods, r["passages"])} for r in bot_rows]
    agent = [{"id": r["id"], **measures(agent_rows[r["id"]], by_case[r["id"]], h.foods, None)} for r in bot_rows]
    meta = {"started": started.strftime("%Y-%m-%d %H:%M"), "model": h.settings.gemini_model, "agent_run": args.agent_run.name,
            "judge": f"{judge_model.get_model_name()}, rúbrica {RUBRIC_VERSION}" if judge else None, "criteria": list(CRITERIA), "errors": errors}  # fmt: skip
    stem = RESULTS / f"{started.strftime('%Y%m%d-%H%M%S')}-baseline"
    stem.with_suffix(".json").write_text(
        json.dumps(
            {"meta": meta, "chatbot": bot_rows, "measures": {"chatbot": bot, "agent": agent}},
            ensure_ascii=False,
            indent=1,
            default=str,
        )
    )
    stem.with_suffix(".md").write_text(table(agent, bot, meta))
    print(table(agent, bot, meta))


if __name__ == "__main__":
    asyncio.run(main())
