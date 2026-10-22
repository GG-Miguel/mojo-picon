"""Retrieval quality of the RAG: what it brings back, passage by passage, with the standard metrics.

The rag set (evals/cases/rag.yaml) only checked that the expected guide is among the first 3 passages.
This script looks at every passage of the top 5, for the three search modes (hybrid, the one in
production; dense; sparse/BM25), and the judge (Vertex AI) decides whether each passage helps to
answer the question. From that:

- by document: Hit@1, Hit@3, Hit@5 and MRR of the expected guide (no judge needed);
- by passage: Precision@1, @3 and @5, MRR of the first relevant passage and nDCG@5 (binary relevance;
  the ideal ranking uses every passage judged relevant for that question in any mode), and the
  questions with no relevant passage at all in the top 5.

    evals/retrieval.sh
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from evals.cases import load
from evals.judge import _json_block, make_judge
from mojo_picon.config import Settings
from mojo_picon.rag.index import guide_index_from_settings

RESULTS = Path(__file__).parent / "results"
MODES = ("hybrid", "dense", "sparse")
K = 5
MAX_PASSAGE_CHARS = 6000  # passages are up to ~4,000 characters (median 1,941): the judge reads them whole
PROMPT = """Evalúas un buscador de guías de nutrición. Pregunta de un usuario:
«{question}»

Pasaje recuperado ({tag}):
«{text}»

¿El pasaje contiene información que ayuda a responder esta pregunta concreta (un dato, una pauta o una
recomendación sobre lo que se pregunta)? Un pasaje del mismo tema general que no responde a lo que se
pregunta no es relevante. Devuelve {{"relevante": true|false, "motivo": "una frase"}}."""


class Relevance(BaseModel):
    relevante: bool
    motivo: str = ""


def parse(text: str) -> Relevance:
    return Relevance.model_validate_json(_json_block(text))


def dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    out = {f"hit@{k}": sum(r["doc_rank"] is not None and r["doc_rank"] <= k for r in rows) / n for k in (1, 3, 5)}
    out["mrr_doc"] = sum(1 / r["doc_rank"] for r in rows if r["doc_rank"]) / n
    for k in (1, 3, 5):
        out[f"precision@{k}"] = sum(sum(r["relevant"][:k]) / k for r in rows) / n
    out["mrr"] = sum(1 / (r["relevant"].index(1) + 1) for r in rows if 1 in r["relevant"]) / n
    out["ndcg@5"] = sum(dcg(r["relevant"]) / dcg([1] * min(r["pool"], K)) for r in rows if r["pool"]) / n
    out["sin_pasaje_relevante"] = sum(1 not in r["relevant"] for r in rows)
    return out


async def main() -> None:
    settings = Settings.from_env()
    index = guide_index_from_settings(settings)
    if index is None:
        raise SystemExit("Qdrant is not configured (QDRANT_URL, QDRANT_API_KEY)")
    judge = make_judge()
    cases = load("rag")
    judged: dict[tuple[str, str], Relevance] = {}
    semaphore = asyncio.Semaphore(4)

    async def relevance(question: str, tag: str, text: str) -> Relevance:
        key = (question, tag)
        if key not in judged:
            async with semaphore:
                prompt = PROMPT.format(question=question, tag=tag, text=text[:MAX_PASSAGE_CHARS])
                for attempt in range(3):
                    try:
                        judged[key] = parse(await judge.a_generate(prompt + "\n\nResponde solo con el objeto JSON."))
                        break
                    except ValueError:  # invalid or empty JSON from the judge
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2)
        return judged[key]

    async def search(question: str, mode: str):
        for attempt in range(3):  # Qdrant Cloud timed out once in a run (22 Oct)
            try:
                return await index.search(question, k=K, mode=mode)
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(5)

    retrieved = {}
    for case in cases:
        for mode in MODES:
            retrieved[case["id"], mode] = await search(case["pregunta"], mode)
    await asyncio.gather(*(relevance(c["pregunta"], h.tag, h.text) for c in cases for m in MODES
                           for h in retrieved[c["id"], m]))  # fmt: skip

    by_mode: dict[str, list[dict]] = {m: [] for m in MODES}
    for case in cases:
        pool = {tag for (q, tag), r in judged.items() if q == case["pregunta"] and r.relevante}
        for mode in MODES:
            hits = retrieved[case["id"], mode]
            tags = [h.tag for h in hits]
            doc_rank = next((i + 1 for i, t in enumerate(tags) if any(t.startswith(s) for s in case["fuente"])), None)
            by_mode[mode].append({
                "id": case["id"], "tags": tags, "doc_rank": doc_rank, "pool": len(pool),
                "relevant": [int(judged[case["pregunta"], t].relevante) for t in tags],
                "motivos": [judged[case["pregunta"], t].motivo for t in tags],
            })  # fmt: skip
    summary = {mode: metrics(rows) for mode, rows in by_mode.items()}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS.mkdir(exist_ok=True)
    meta = {"judge": judge.get_model_name(), "k": K, "casos": len(cases)}
    (RESULTS / f"{stamp}-retrieval.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "cases": by_mode}, ensure_ascii=False, indent=1)
    )
    text = report(summary, by_mode, meta)
    (RESULTS / f"{stamp}-retrieval.md").write_text(text)
    print(text)


def report(summary: dict, by_mode: dict, meta: dict) -> str:
    names = {"hybrid": "híbrida (producción)", "dense": "densa", "sparse": "léxica (BM25)"}
    lines = [
        f"# Recuperación del RAG · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"{meta['casos']} preguntas, los {meta['k']} primeros pasajes de cada modo; relevancia de cada pasaje "
        f"decidida por el juez ({meta['judge']}).",
        "",
        "| Búsqueda | Hit@1 | Hit@3 | Hit@5 | MRR doc. | P@1 | P@3 | P@5 | MRR pasaje | nDCG@5 | Sin pasaje útil |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, s in summary.items():
        lines.append(
            f"| {names[mode]} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | {s['hit@5']:.2f} | {s['mrr_doc']:.2f} | "
            f"{s['precision@1']:.2f} | {s['precision@3']:.2f} | {s['precision@5']:.2f} | {s['mrr']:.2f} | "
            f"{s['ndcg@5']:.2f} | {s['sin_pasaje_relevante']} |"
        )
    lines += ["", "## Pasajes de la búsqueda híbrida", "", "✓ relevante según el juez · ✗ no relevante", ""]
    for r in by_mode["hybrid"]:
        marks = " · ".join(f"{'✓' if g else '✗'} {t}" for g, t in zip(r["relevant"], r["tags"], strict=True))
        lines.append(f"- **{r['id']}**: {marks}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
