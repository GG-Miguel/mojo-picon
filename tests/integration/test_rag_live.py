"""Acceptance of the basic RAG (Tareas Hito 1): 5 questions return the right source.

Needs QDRANT_URL, QDRANT_API_KEY and Vertex AI credentials; the index is built by ingest_rag.py.
"""

import pytest

from mojo_picon.config import Settings
from mojo_picon.rag.index import guide_index_from_settings

pytestmark = pytest.mark.integration

QUESTIONS = [
    ("¿Cuánta proteína al día necesita alguien que entrena fuerza?", "ISSN proteína 2017"),
    ("¿Qué dosis de cafeína mejora el rendimiento y cuánto antes de entrenar?", "ISSN cafeína 2021"),
    ("adequate intake of water for adult men and women", "EFSA DRV 2017"),
    ("¿Cuántos minutos de actividad física moderada a la semana recomienda la OMS a los adultos?", "OMS"),
    ("¿Cuántas raciones de legumbres a la semana se recomiendan en España?", "AESAN 2022"),
]


@pytest.fixture  # per test: the async clients are bound to the event loop of the test
def index():
    index = guide_index_from_settings(Settings.from_env())
    if index is None:
        pytest.skip("QDRANT_URL and QDRANT_API_KEY are not set")
    return index


@pytest.mark.parametrize(("question", "source"), QUESTIONS)
async def test_the_right_source_is_in_the_top_4(index, question, source):
    hits = await index.search(question)
    assert any(h.tag.startswith(source) for h in hits), [h.tag for h in hits]
