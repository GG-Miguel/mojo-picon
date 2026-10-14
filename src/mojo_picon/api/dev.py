"""Local development server: real agents (Gemini) without Firebase login (milestone 1).

    API_DEV_TOKENS="dev-token-ana:ana" STORE=memory uv run uvicorn mojo_picon.api.dev:app --port 8080

Tokens come from API_DEV_TOKENS ("token:uid,…"); refused when ENVIRONMENT=production. STORE=memory
creates a demo profile for each development user; STORE=firestore uses the real database.
"""

from __future__ import annotations

import hmac
from pathlib import Path

from mojo_picon.agents import build_graph
from mojo_picon.agents.knowledge import load_expert_brief
from mojo_picon.api.app import AppDeps, create_app
from mojo_picon.auth import InvalidTokenError, UserContext
from mojo_picon.config import Settings
from mojo_picon.devtools import dev_store, require_development
from mojo_picon.llm import GeminiProvider
from mojo_picon.observability import tracer_from_settings
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods


class DevTokenVerifier:
    def __init__(self, tokens: dict[str, str]):
        self._tokens = tokens

    async def verify(self, token: str) -> UserContext:
        for known, uid in self._tokens.items():
            if hmac.compare_digest(known, token):
                return UserContext(uid=uid)
        raise InvalidTokenError("unknown development token")


def build_dev_app(settings: Settings):
    require_development(settings, "The development API")
    foods = load_foods()
    models = GeminiProvider.from_settings(settings)
    brief, passages = load_expert_brief()
    deps = AppDeps(
        verifier=DevTokenVerifier(settings.api_dev_tokens),
        store=dev_store(settings, set(settings.api_dev_tokens.values())),
        foods=foods,
        activities=load_met_table(),
        graph=build_graph(models, foods),
        models=models,
        tracer=tracer_from_settings(settings),
        expert_brief=brief,
        brief_passages=passages,
        frontend_dir=Path(settings.frontend_dir) if settings.frontend_dir else None,
    )
    return create_app(deps)


app = build_dev_app(Settings.from_env())
