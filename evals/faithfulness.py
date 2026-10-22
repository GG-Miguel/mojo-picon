"""Faithfulness of the answers to the sources they cite (DeepEval FaithfulnessMetric, Vertex judge).

The number checker already proves that every figure has an origin; this measures the rest of the
answer. The Coach, as in production, answers the 30 questions of the rag set, which are about the
guidelines. The retrieval context of each answer is the text of every source it cites: lines of the
expert brief or passages of the guideline index (Qdrant). The judge splits the answer into claims and
checks each one against that context; a claim with no support in what was cited counts as unfaithful,
which is how an answer that invents or overstates a guideline shows up.

    evals/faithfulness.sh                                  # the Coach answers, then the judge scores
    evals/faithfulness.sh --rescore <run>-faithfulness.json  # score the saved answers again (missing ones)
    evals/faithfulness.sh --rescore <run>-faithfulness.json --control
        # control: each answer with a false claim added; a useful metric must drop below 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase
from qdrant_client import AsyncQdrantClient

from evals.cases import load
from evals.harness import Harness
from evals.judge import make_judge
from mojo_picon.guardrails.number_origin import citations, index_brief
from mojo_picon.rag.index import COLLECTION

RESULTS = Path(__file__).parent / "results"
ANSWER_TIMEOUT = 300  # seconds to score one answer; past that it is reported without a score
BRIEF = Path(__file__).parents[1] / "knowledge" / "expert_brief.md"


async def guide_passages(settings) -> dict[str, str]:
    """Every passage of the guideline index: citation tag (lower case) -> text."""
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=30)
    passages: dict[str, str] = {}
    offset = None
    while True:
        points, offset = await client.scroll(COLLECTION, limit=256, offset=offset, with_payload=True)
        for p in points:
            passages[p.payload["tag"].lower()] = p.payload["text"]
        if offset is None:
            return passages


CONTROL = " Además, la OMS recomienda tomar 4 g de proteína por kg de peso al día y beber al menos 6 litros de agua."


async def score(judge, question: str, answer: str, context: list[str]) -> dict:
    for attempt in range(3):  # the judge's JSON breaks now and then; DeepEval does not retry
        # A claim the sources do not mention is "idk" for DeepEval and, by default, does not lower the
        # score: an invented guideline would pass (22 Oct, control with a false claim: still 1.00).
        metric = FaithfulnessMetric(model=judge, include_reason=True, async_mode=True, penalize_ambiguous_claims=True)
        try:
            await metric.a_measure(LLMTestCase(input=question, actual_output=answer, retrieval_context=context))
        except Exception as e:
            if attempt == 2:
                return {"faithfulness": None, "motivo": f"error del juez: {str(e)[:120]}"}
            await asyncio.sleep(3)
            continue
        unsupported = [v.reason for v in (metric.verdicts or []) if v.verdict.strip().lower() == "no"]
        return {"faithfulness": metric.score, "motivo": metric.reason, "no_apoyadas": unsupported}
    raise AssertionError("unreachable")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rescore", type=Path, help="a previous *-faithfulness.json: score its answers")
    parser.add_argument("--control", action="store_true", help="with --rescore: add a false claim to each answer")
    args = parser.parse_args()
    h = Harness()
    judge = make_judge()
    sources = {**await guide_passages(h.settings),
               **{t.lower(): text for t, text in index_brief(BRIEF.read_text()).items()}}  # fmt: skip
    semaphore = asyncio.Semaphore(4)

    async def one(case: dict, previous: dict | None) -> dict:
        async with semaphore:
            if previous is None:
                run = await h.chat({"id": case["id"]}, [case["pregunta"]])
                answer = run.turns[-1].answer
            else:
                answer = previous["respuesta"] + (CONTROL if args.control else "")
                if previous.get("faithfulness") is not None and not args.control:
                    return previous  # already scored
            cited = sorted({c.lower() for c in citations(answer)})
            context = [sources[c] for c in cited if c in sources]
            row = {"id": case["id"], "pregunta": case["pregunta"], "respuesta": answer, "citas": cited,
                   "citas_sin_texto": [c for c in cited if c not in sources]}  # fmt: skip
            if not context:
                return progress({**row, "faithfulness": None, "motivo": "la respuesta no cita ninguna fuente"})
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(score(judge, case["pregunta"], answer, context), ANSWER_TIMEOUT)
            except TimeoutError:
                result = {"faithfulness": None, "motivo": f"tiempo agotado ({ANSWER_TIMEOUT} s)"}
            return progress({**row, **result}, time.monotonic() - start)

    done = 0

    def progress(row: dict, seconds: float = 0) -> dict:
        """One line per answer as it is scored, so a slow judge shows instead of a silent run."""
        nonlocal done
        done += 1
        value = "—" if row["faithfulness"] is None else f"{row['faithfulness']:.2f}"
        print(f"[{done}/{len(cases)}] {row['id']} faithfulness {value} ({seconds:.0f} s)", file=sys.stderr, flush=True)
        return row

    previous = {}
    if args.rescore:
        previous = {r["id"]: r for r in json.loads(args.rescore.read_text())["rows"]}
    cases = [c for c in load("rag") if not args.rescore or c["id"] in previous]
    rows = await asyncio.gather(*(one(c, previous.get(c["id"]) if args.rescore else None) for c in cases))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-control" if args.control else "")
    RESULTS.mkdir(exist_ok=True)
    meta = {"judge": judge.get_model_name(), "models": h.settings.role_models | {"coach": h.settings.gemini_model},
            "control": args.control, "rescore": str(args.rescore or "")}  # fmt: skip
    data = json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=1)
    (RESULTS / f"{stamp}-faithfulness.json").write_text(data)
    text = report(rows, meta)
    (RESULTS / f"{stamp}-faithfulness.md").write_text(text)
    print(text)


def report(rows: list[dict], meta: dict) -> str:
    scored = [r for r in rows if r["faithfulness"] is not None]
    full = sum(r["faithfulness"] == 1 for r in scored)
    mean = sum(r["faithfulness"] for r in scored) / len(scored) if scored else 0
    no_cite = sum(not r["citas"] for r in rows)
    lines = [
        f"# Fidelidad a las fuentes citadas · {datetime.now():%Y-%m-%d %H:%M}"
        + (" · control con una afirmación falsa añadida" if meta.get("control") else ""),
        "",
        f"{len(rows)} preguntas del conjunto del RAG respondidas por el Coach; juez {meta['judge']}. "
        f"Con fuentes citadas: {len(scored)}. Faithfulness media {mean:.2f}; todas las afirmaciones apoyadas en "
        f"{full} de {len(scored)}. Respuestas sin ninguna cita: {no_cite}.",
        "",
        "| Caso | Faithfulness | Citas | Afirmaciones sin apoyo |",
        "|---|---|---|---|",
    ]
    for r in rows:
        score = "—" if r["faithfulness"] is None else f"{r['faithfulness']:.2f}"
        missing = " / ".join(r.get("no_apoyadas", []))[:300] or r.get("motivo", "") if r["faithfulness"] != 1 else ""
        lines.append(f"| {r['id']} | {score} | {len(r['citas'])} | {missing.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
