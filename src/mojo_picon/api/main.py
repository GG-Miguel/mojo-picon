"""Production entry point: `uvicorn mojo_picon.api.main:app`.

Configuration from the environment (config.Settings): Firebase token verification, Firestore,
Gemini through the Vertex AI EU endpoint, Langfuse if its keys are set, the guideline index
(Qdrant) if its URL and key are set.
"""

from __future__ import annotations

from pathlib import Path

from mojo_picon.agents import build_graph
from mojo_picon.agents.knowledge import load_expert_brief
from mojo_picon.api.app import AppDeps, create_app
from mojo_picon.auth import FirebaseTokenVerifier
from mojo_picon.config import Settings
from mojo_picon.llm import GeminiProvider
from mojo_picon.observability import tracer_from_settings
from mojo_picon.rag.index import guide_index_from_settings
from mojo_picon.store.firestore import FirestoreStore
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods


def build_app(settings: Settings):
    foods = load_foods()
    models = GeminiProvider.from_settings(settings)
    brief, passages = load_expert_brief()
    deps = AppDeps(
        verifier=FirebaseTokenVerifier(project_id=settings.gcp_project_id),
        store=FirestoreStore.connect(project_id=settings.gcp_project_id, database=settings.firestore_database),
        foods=foods,
        activities=load_met_table(),
        graph=build_graph(models, foods),
        models=models,
        guides=guide_index_from_settings(settings),
        tracer=tracer_from_settings(settings),
        expert_brief=brief,
        brief_passages=passages,
        frontend_dir=Path(settings.frontend_dir) if settings.frontend_dir else None,
        production=settings.is_production,
        auth_proxy_host=f"{settings.gcp_project_id}.firebaseapp.com",
    )
    return create_app(deps)


app = build_app(Settings.from_env())
