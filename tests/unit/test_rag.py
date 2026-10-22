import dataclasses
import hashlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from qdrant_client import AsyncQdrantClient
from tests.fakes import FakeProvider, consented, tool_call
from tests.unit.test_agents import OK, context  # noqa: F401  (fixture)

from mojo_picon.agents import build_graph
from mojo_picon.guardrails.output import FEEDBACK_NAME
from mojo_picon.rag import sparse
from mojo_picon.rag.chunks import chunk_document
from mojo_picon.rag.documents import Section, html_sections, jats_sections, page_sections
from mojo_picon.rag.index import GuideHit, GuideIndex
from mojo_picon.rag.transcribe import page_number_mismatches
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
GUIDE = {
    "id": "efsa",
    "tag": "EFSA DRV 2017",
    "title": "DRVs",
    "year": 2017,
    "license": "© EFSA",
    "url": "https://example.org/efsa.pdf",
    "language": "en",
}


# --- parsing ------------------------------------------------------------------------------

FACT_SHEET = """<html><body><nav><p>Menú</p></nav>
<article class="sf-detail-body-wrapper">
<h2>Datos y cifras</h2><ul><li>Menos del 10 % de azúcares libres.</li></ul>
<h2>Grasas</h2><p>Las grasas no deberían superar el 30 %.</p><h3>Trans</h3><p>Menos del 1 %.</p>
<h2>Referencias bibliográficas</h2><p>1. Una referencia.</p>
</article><footer><p>Pie</p></footer></body></html>"""


def test_fact_sheet_sections_keep_the_article_only():
    sections = html_sections(FACT_SHEET)
    assert [s.heading for s in sections] == ["Datos y cifras", "Grasas"]
    assert sections[0].text == "- Menos del 10 % de azúcares libres."
    assert "### Trans" in sections[1].text and "Menú" not in str(sections) and "referencia" not in str(sections)


JATS = """<article><front><article-meta><abstract><p>Protein 1.4–2.0 g/kg/d.</p></abstract></article-meta></front>
<body>
<sec><title>Protein intake</title><p>Intakes of 1.4–2.0 g/kg/d <xref>[12]</xref> are sufficient.
<table-wrap><caption><p>Table 1 Leucine</p></caption><table><tr><th>Food</th><th>g</th></tr>
<tr><td>Whey</td><td>2.5</td></tr></table></table-wrap></p>
<sec><title>Timing</title><p>Every 3–4 h.</p></sec></sec>
<sec><title>Competing interests</title><p>None.</p></sec>
</body><back><ref-list><ref>Ref</ref></ref-list></back></article>"""


def test_jats_sections_keep_tables_and_drop_reference_markers():
    sections = jats_sections(JATS)
    assert [(s.locator, s.heading) for s in sections] == [("§0", "Abstract"), ("§1", "Protein intake")]
    text = sections[1].text
    assert "[12]" not in text and "1.4–2.0 g/kg/d are sufficient" in text
    assert "| Whey | 2.5 |" in text and "**Table 1 Leucine**" in text
    assert "### Timing" in text


def test_transcribed_pages_become_page_sections():
    assert page_sections(["texto", "", "más"]) == [Section("p. 1", "", "texto"), Section("p. 3", "", "más")]


def test_transcription_numbers_are_checked_against_the_pdf_text():
    assert page_number_mismatches("800 to 1,000 mL/day", "800 \nto 1 ,000 mL/day") == set()
    assert page_number_mismatches("(35, 121, 122)", "(35, 121, 122)") == set()
    assert page_number_mismatches("2.5 L of water", "2.0 L of water") == {"25"}  # misread number
    assert page_number_mismatches("anything 7", "") == set()  # nothing to compare with (scanned page)


# --- chunking -----------------------------------------------------------------------------


def test_chunks_carry_the_citation_tag_and_metadata():
    [chunk] = chunk_document(GUIDE, [Section("p. 21", "Water", "Adults: 2.5 L/day.")])
    assert chunk.tag == "EFSA DRV 2017, p. 21"
    assert chunk.text.startswith("## Water") and chunk.year == 2017 and chunk.license == "© EFSA"


def test_long_sections_are_split_but_tables_never():
    table = "\n".join(["| Age | AI |", "|---|---|"] + [f"| {i} | {i * 100} mL |" for i in range(40)])
    text = "\n\n".join([f"Paragraph {i}. " + "x" * 300 for i in range(6)] + [table])
    chunks = chunk_document(GUIDE, [Section("p. 5", "", text)], max_chars=800)
    assert len(chunks) > 2
    assert [c.locator for c in chunks][:2] == ["p. 5.1", "p. 5.2"]
    with_table = [c for c in chunks if "| Age | AI |" in c.text]
    assert len(with_table) == 1 and "| 39 | 3900 mL |" in with_table[0].text


def test_point_ids_are_stable():
    a = chunk_document(GUIDE, [Section("p. 1", "", "Same text.")])[0]
    b = chunk_document(GUIDE, [Section("p. 1", "", "Same text.")])[0]
    assert a.point_id == b.point_id


# --- BM25 ---------------------------------------------------------------------------------


def test_bm25_ignores_accents_case_and_stop_words():
    assert sparse.tokenize("La Proteína y la CAFEÍNA") == ["proteina", "cafeina"]
    assert sparse.tokenize("1.4 g/kg") == ["1.4", "kg"]
    assert sparse.query_vector("cafeína")[0] == sparse.document_vector("Cafeina")[0]


# --- index (Qdrant in memory) -------------------------------------------------------------


class HashEmbedder:
    """Deterministic bag-of-words embedding: close texts get close vectors, no network."""

    dimension = 64

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in sparse.tokenize(text):
            vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimension] += 1.0
        return vector if any(vector) else [1.0] + [0.0] * (self.dimension - 1)

    async def aembed_documents(self, texts):
        return [self._embed(t) for t in texts]

    async def aembed_query(self, text):
        return self._embed(text)


async def test_hybrid_search_finds_the_right_passage():
    sections = [
        Section("p. 1", "Water", "Adequate intake of water for adults: 2.5 L/day for men."),
        Section("p. 2", "Caffeine", "Caffeine doses of 3–6 mg/kg improve endurance performance."),
        Section("p. 3", "Protein", "Protein intakes of 1.4–2.0 g/kg/d for exercising individuals."),
    ]
    index = GuideIndex(AsyncQdrantClient(":memory:"), HashEmbedder(), collection="test")
    await index.rebuild(chunk_document(GUIDE, sections), HashEmbedder.dimension)
    hits = await index.search("caffeine and endurance", k=2)
    assert hits[0].tag == "EFSA DRV 2017, p. 2"
    await index.rebuild(chunk_document(GUIDE, sections[:1]), HashEmbedder.dimension)  # idempotent rebuild
    assert [h.tag for h in await index.search("caffeine")] == ["EFSA DRV 2017, p. 1"]


# --- the Coach with search_guides ---------------------------------------------------------

PASSAGE = "Water: adequate intake 2.5 L/day for adult men."


class FakeGuides:
    def __init__(self):
        self.queries = []

    async def search(self, query, k=4):
        self.queries.append(query)
        return [GuideHit(tag="EFSA DRV 2017, p. 21", text=PASSAGE, title="DRVs", url="u", score=1.0)]


async def run_with_guides(context, guides, answers):  # noqa: F811
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("search_guides", "g1", query="water adequate intake adults"), *map(AIMessage, answers)],
    )
    ctx = dataclasses.replace(context, guides=guides)
    state = await build_graph(models, FOODS).ainvoke({"messages": [HumanMessage("¿Cuánta agua bebo?")]}, context=ctx)
    return state, models


async def test_a_cited_passage_is_a_valid_origin_for_its_numbers(context):  # noqa: F811
    guides = FakeGuides()
    answer = "La EFSA da 2,5 L al día para hombres adultos [EFSA DRV 2017, p. 21]."
    state, _ = await run_with_guides(context, guides, [answer])
    assert guides.queries == ["water adequate intake adults"]
    assert state["sources"] == {"EFSA DRV 2017, p. 21": PASSAGE}
    assert state["messages"][-1].text == answer


async def test_a_passage_number_without_its_citation_is_not_accepted(context):  # noqa: F811
    state, _ = await run_with_guides(
        context, FakeGuides(), ["Bebe 2,5 L al día.", "Bebe 2,5 L al día [EFSA DRV 2017, p. 21]."]
    )
    feedback = [m for m in state["messages"] if isinstance(m, HumanMessage) and m.name == FEEDBACK_NAME]
    assert len(feedback) == 1  # regenerated once, then accepted with the citation
    assert state["messages"][-1].text.endswith("[EFSA DRV 2017, p. 21].")


async def test_without_an_index_the_tool_says_so(context):  # noqa: F811
    state, _ = await run_with_guides(context, None, ["No tengo la fuente a mano."])
    tool_message = next(m for m in state["messages"] if getattr(m, "name", None) == "search_guides")
    assert "no están disponibles" in tool_message.text
    assert not state.get("sources")


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_queries_have_no_sparse_terms(query):
    assert sparse.query_vector(query) == ([], [])


# --- sources shown under the answer -------------------------------------------------------


def test_only_the_cited_documents_are_listed_as_sources():
    import json

    from mojo_picon.api.app import _cited_sources, _passage_documents

    result = json.dumps(
        {
            "pasajes": [
                {"etiqueta": "EFSA DRV 2017, p. 21", "documento": "DRVs", "url": "https://efsa", "texto": "x"},
                {"etiqueta": "EFSA DRV 2017, p. 23", "documento": "DRVs", "url": "https://efsa", "texto": "y"},
                {"etiqueta": "ISSN cafeína 2021, §3", "documento": "Caffeine", "url": "https://issn", "texto": "z"},
            ]
        }
    )
    retrieved = _passage_documents(result)
    [source] = _cited_sources("Bebe 2,5 L al día [EFSA DRV 2017, p. 21].", retrieved)
    assert (source.title, source.url, source.tags) == ("DRVs", "https://efsa", ["EFSA DRV 2017, p. 21"])
    [whole] = _cited_sources("Según la EFSA [EFSA DRV 2017].", retrieved)  # a document-level citation
    assert whole.tags == ["EFSA DRV 2017, p. 21", "EFSA DRV 2017, p. 23"]
    assert _cited_sources("Sin citas.", retrieved) == []
    assert _passage_documents("no es JSON") == {}


async def test_parallel_searches_stream_and_cite_through_the_api():
    import httpx
    from tests.unit.test_api import ANA, FakeVerifier, events

    from mojo_picon.agents import build_graph as build
    from mojo_picon.api.app import AppDeps, create_app
    from mojo_picon.auth import UserContext
    from mojo_picon.domain import Profile, Sex
    from mojo_picon.observability import NullTracer
    from mojo_picon.store import InMemoryStore
    from mojo_picon.tools.energy import load_met_table

    two_searches = AIMessage(
        "",
        tool_calls=[
            {"name": "search_guides", "args": {"query": "caffeine"}, "id": "g1"},
            {"name": "search_guides", "args": {"query": "water"}, "id": "g2"},
        ],
    )
    models = FakeProvider(guardian=[OK], coach=[two_searches, AIMessage("Bebe 2,5 L al día [EFSA DRV 2017, p. 21].")])
    store = InMemoryStore()
    await consented(store, "ana")
    await store.save_profile(UserContext(uid="ana"), Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175))
    deps = AppDeps(
        verifier=FakeVerifier(), store=store, foods=FOODS, activities=load_met_table(),
        graph=build(models, FOODS), tracer=NullTracer(), guides=FakeGuides(),
    )  # fmt: skip
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(deps)), base_url="http://t") as client:
        stream = events(await client.post("/chat", headers=ANA, data={"message": "¿Cafeína y agua?"}))
    assert not [e for e in stream if e["type"] == "error"]
    final = next(e for e in stream if e["type"] == "final")
    assert final["sources"] == [{"title": "DRVs", "url": "u", "tags": ["EFSA DRV 2017, p. 21"]}]
