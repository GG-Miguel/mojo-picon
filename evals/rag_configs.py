"""RAG experiment: dense, sparse (BM25) and hybrid search on the RAG cases (Evidencias: «RAG»).

    evals/run.sh is not needed: uv run --group eval python -m evals.rag_configs   (needs QDRANT_URL/KEY)

recall@3: the expected guideline is among the first 3 passages. precision@3: share of the first 3
passages that come from an expected guideline (the noise the Coach would read).
"""

from __future__ import annotations

import asyncio

from evals.cases import load
from mojo_picon.config import Settings
from mojo_picon.rag.index import guide_index_from_settings

MODES = ["dense", "sparse", "hybrid"]


async def main() -> None:
    index = guide_index_from_settings(Settings.from_env())
    cases = load("rag")
    print("| Configuración | recall@1 | recall@3 | precisión@3 |\n| --- | --- | --- | --- |")
    for mode in MODES:
        r1 = r3 = relevant = 0
        for case in cases:
            tags = [h.tag for h in await index.search(case["pregunta"], k=3, mode=mode)]
            ok = [any(t.startswith(s) for s in case["fuente"]) for t in tags]
            r1 += ok[0]
            r3 += any(ok)
            relevant += sum(ok)
        n = len(cases)
        print(f"| {mode} | {r1} de {n} | {r3} de {n} | {100 * relevant / (3 * n):.0f} % |")


if __name__ == "__main__":
    asyncio.run(main())
