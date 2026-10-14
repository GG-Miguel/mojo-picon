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


@dataclass(frozen=True)
class Settings:
    environment: str = "development"  # development | staging | production
    gcp_project_id: str = "mojo-picon"
    firestore_database: str = "mojopicon"
    vertex_location: str = "eu"
    vertex_endpoint: str = "https://aiplatform.eu.rep.googleapis.com"
    gemini_model: str = "gemini-3.8-flash"
    store: str = "firestore"  # firestore | memory (development only)
    frontend_dir: str = ""  # compiled React app served by the API (set in the container image)
    langfuse_enabled: bool = False
    api_dev_tokens: dict[str, str] = field(default_factory=dict)
    mcp_dev_tokens: dict[str, str] = field(default_factory=dict)

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
            store=env.get("STORE", defaults.store),
            frontend_dir=env.get("FRONTEND_DIR", defaults.frontend_dir),
            langfuse_enabled=bool(env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY")),
            api_dev_tokens=_pairs(env.get("API_DEV_TOKENS", "")),
            mcp_dev_tokens=_pairs(env.get("MCP_DEV_TOKENS", "")),
        )
