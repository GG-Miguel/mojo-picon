"""Production entry point: `uvicorn mojo_picon.api.main:app`.

Configuration from the environment (config.Settings): Firebase token verification, Firestore,
Gemini through the Vertex AI EU endpoint, Langfuse if its keys are set.
"""

from __future__ import annotations

from mojo_picon.agents import build_graph
from mojo_picon.agents.knowledge import load_expert_brief
from mojo_picon.api.app import AppDeps, create_app
from mojo_picon.auth import FirebaseTokenVerifier
from mojo_picon.config import Settings
from mojo_picon.llm import GeminiProvider
from mojo_picon.observability import tracer_from_settings
from mojo_picon.store.firestore import FirestoreStore
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods


def build_app(settings: Settings):
    foods = load_foods()
    brief, passages = load_expert_brief()
    deps = AppDeps(
        verifier=FirebaseTokenVerifier(project_id=settings.gcp_project_id),
        store=FirestoreStore.connect(project_id=settings.gcp_project_id, database=settings.firestore_database),
        foods=foods,
        activities=load_met_table(),
        graph=build_graph(GeminiProvider.from_settings(settings), foods),
        tracer=tracer_from_settings(settings),
        expert_brief=brief,
        brief_passages=passages,
    )
    return create_app(deps)


app = build_app(Settings.from_env())
