"""Guideline index in Qdrant: dense (gemini-embedding-2) + sparse (BM25) vectors in one collection,
fused by Qdrant with RRF (ADR-08, ADR-22). The index holds only public guidelines, no user data.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from qdrant_client import AsyncQdrantClient, models

from mojo_picon.rag import sparse
from mojo_picon.rag.chunks import Chunk

COLLECTION = "guides"
DENSE = "dense"
SPARSE = "bm25"
TOP_K = 4
PREFETCH = 20  # candidates per search before fusion
EMBED_BATCH = 50  # points per upsert
EMBED_CONCURRENCY = 8  # gemini-embedding-2 on Vertex AI embeds one text per call


class Embedder(Protocol):
    """LangChain embeddings interface (GoogleGenerativeAIEmbeddings in production)."""

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def aembed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class GuideHit:
    tag: str
    text: str
    title: str
    url: str
    score: float


class GuideSearch(Protocol):
    async def _embed_document(self, text: str) -> list[float]:
        async with self._semaphore:
            for attempt in range(4):
                try:
                    [vector] = await self._embedder.aembed_documents([text])
                    return vector
                except Exception:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2**attempt)
        raise AssertionError("unreachable")

    async def search(self, query: str, k: int = TOP_K) -> list[GuideHit]: ...


class GuideIndex:
    def __init__(self, client: AsyncQdrantClient, embedder: Embedder, collection: str = COLLECTION):
        self._client = client
        self._embedder = embedder
        self._collection = collection
        self._semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def rebuild(self, chunks: list[Chunk], dimension: int) -> None:
        """Drop and create the collection, then index every chunk (idempotent ingestion)."""
        if await self._client.collection_exists(self._collection):
            await self._client.delete_collection(self._collection)
        await self._client.create_collection(
            self._collection,
            vectors_config={DENSE: models.VectorParams(size=dimension, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            dense = await asyncio.gather(*(self._embed_document(c.text) for c in batch))
            points = []
            for chunk, vector in zip(batch, dense, strict=True):
                indices, values = sparse.document_vector(chunk.text)
                points.append(
                    models.PointStruct(
                        id=chunk.point_id,
                        vector={DENSE: vector, SPARSE: models.SparseVector(indices=indices, values=values)},
                        payload=chunk.payload(),
                    )
                )
            await self._client.upsert(self._collection, points=points)

    async def _embed_document(self, text: str) -> list[float]:
        async with self._semaphore:
            for attempt in range(4):
                try:
                    [vector] = await self._embedder.aembed_documents([text])
                    return vector
                except Exception:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2**attempt)
        raise AssertionError("unreachable")

    async def search(self, query: str, k: int = TOP_K) -> list[GuideHit]:
        dense = await self._embedder.aembed_query(query)
        indices, values = sparse.query_vector(query)
        prefetch = [models.Prefetch(query=dense, using=DENSE, limit=PREFETCH)]
        if indices:
            prefetch.append(
                models.Prefetch(query=models.SparseVector(indices=indices, values=values), using=SPARSE, limit=PREFETCH)
            )
        result = await self._client.query_points(
            self._collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=k,
            with_payload=True,
        )
        return [
            GuideHit(
                tag=p.payload["tag"],
                text=p.payload["text"],
                title=p.payload["title"],
                url=p.payload["url"],
                score=p.score,
            )
            for p in result.points
        ]


def guide_index_from_settings(settings) -> GuideIndex | None:
    """The guideline index if Qdrant is configured; None: the Coach works with the expert brief only."""
    if not (settings.qdrant_url and settings.qdrant_api_key):
        return None
    from mojo_picon.llm import gemini_embeddings

    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=10)
    return GuideIndex(client, gemini_embeddings(settings))
