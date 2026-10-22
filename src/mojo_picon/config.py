"""Configuration from environment variables, in one place (see .env.example).

No secrets have defaults here; values that are not secret (project, regions, model) do.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _pairs(value: str) -> dict[str, str]:
    """ "token:uid,token:uid" -> {token: uid} (development tokens)."""
    items = (item.split(":", 1) for item in value.split(",") if ":" in item)
    return {token.strip(): uid.strip() for token, uid in items if token.strip() and uid.strip()}


def _names(value: str) -> list[str]:
    """ "a, b" -> ["a", "b"]; an empty value is an empty list."""
    return [item.strip() for item in value.split(",") if item.strip()]


# Roles of llm.Role, one model each: MODEL_COACH, MODEL_PLANNER, MODEL_GUARDIAN, MODEL_VISION.
ROLES = ("coach", "planner", "guardian", "vision")


@dataclass(frozen=True)
class Settings:
    environment: str = "development"  # development | staging | production
    gcp_project_id: str = "mojo-picon"
    firestore_database: str = "mojopicon"
    vertex_location: str = "eu"
    vertex_endpoint: str = "https://aiplatform.eu.rep.googleapis.com"
    gemini_model: str = "gemini-3.8-flash"
    # A model for one role instead of gemini_model (MODEL_<ROLE>), on the same endpoint (ADR-04). The
    # guardian runs on Flash-Lite since 22 Oct: on the evaluation (3 runs per case) it referred 39 of 39
    # risky requests, blocked no legitimate twin and resisted 33 of 33 attacks, at about a third of the
    # price; the planner on Flash-Lite verified 13 of 29 plans against 30 of 30, so it keeps gemini_model.
    role_models: dict[str, str] = field(default_factory=lambda: {"guardian": "gemini-3.5-flash-lite"})
    llm_gateway: str = "litellm"  # litellm (Gemini, then the fallback) | direct (Gemini without LiteLLM)
    # Tried in order on the EU endpoint when Gemini fails or times out (ADR-04); empty: no fallback.
    # Another Gemini has its own quota (the frequent 429); Claude is another family (an outage of Gemini).
    fallback_models: list[str] = field(default_factory=lambda: ["gemini-3.5-flash", "claude-haiku-4-5@20251001"])
    fallback_location: str = "eu"
    embedding_model: str = "gemini-embedding-2"
    # Embeddings keep their own endpoint: the index was built with gemini-embedding-2, which is served
    # on the EU multi-region endpoint only, even if the chat model moves to a region (ADR-04, plan B).
    embedding_location: str = "eu"
    embedding_endpoint: str = "https://aiplatform.eu.rep.googleapis.com"
    qdrant_url: str = ""  # guideline index (RAG); empty: the Coach works with the expert brief only
    qdrant_api_key: str = field(default="", repr=False)  # secret: Secret Manager / local .env
    store: str = "firestore"  # firestore | memory (development only)
    frontend_dir: str = ""  # compiled React app served by the API (set in the container image)
    langfuse_enabled: bool = False
    api_dev_tokens: dict[str, str] = field(default_factory=dict)
    mcp_dev_tokens: dict[str, str] = field(default_factory=dict)

    def model_for(self, role: str) -> str:
        return self.role_models.get(role, self.gemini_model)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        defaults = cls()
        return cls(
            environment=env.get("ENVIRONMENT", defaults.environment),
            gcp_project_id=env.get("GCP_PROJECT_ID", defaults.gcp_project_id),
            firestore_database=env.get("FIRESTORE_DATABASE", defaults.firestore_database),
            vertex_location=env.get("VERTEX_LOCATION", defaults.vertex_location),
            vertex_endpoint=env.get("VERTEX_ENDPOINT", defaults.vertex_endpoint),
            gemini_model=env.get("GEMINI_MODEL", defaults.gemini_model),
            role_models={
                **defaults.role_models,
                **{r: env[f"MODEL_{r.upper()}"] for r in ROLES if env.get(f"MODEL_{r.upper()}", "").strip()},
            },
            llm_gateway=env.get("LLM_GATEWAY", defaults.llm_gateway),
            fallback_models=_names(env["FALLBACK_MODELS"]) if "FALLBACK_MODELS" in env else defaults.fallback_models,
            fallback_location=env.get("FALLBACK_LOCATION", defaults.fallback_location),
            embedding_model=env.get("EMBEDDING_MODEL", defaults.embedding_model),
            embedding_location=env.get("EMBEDDING_LOCATION", defaults.embedding_location),
            embedding_endpoint=env.get("EMBEDDING_ENDPOINT", defaults.embedding_endpoint),
            qdrant_url=env.get("QDRANT_URL", defaults.qdrant_url),
            qdrant_api_key=env.get("QDRANT_API_KEY", defaults.qdrant_api_key),
            store=env.get("STORE", defaults.store),
            frontend_dir=env.get("FRONTEND_DIR", defaults.frontend_dir),
            langfuse_enabled=bool(env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY")),
            api_dev_tokens=_pairs(env.get("API_DEV_TOKENS", "")),
            mcp_dev_tokens=_pairs(env.get("MCP_DEV_TOKENS", "")),
        )
