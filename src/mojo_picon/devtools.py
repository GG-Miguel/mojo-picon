"""Development helpers shared by the local API and MCP servers. Never used in production."""

from __future__ import annotations

import asyncio

from mojo_picon.auth.context import UserContext
from mojo_picon.config import Settings
from mojo_picon.domain import Profile, Sex
from mojo_picon.store.base import Store
from mojo_picon.store.memory import InMemoryStore

DEMO_PROFILE = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175)


def require_development(settings: Settings, what: str) -> None:
    if settings.is_production:
        raise RuntimeError(f"{what} must not be used in production")


def dev_store(settings: Settings, uids: set[str]) -> Store:
    """Firestore if STORE=firestore; otherwise in memory with the demo profile for each dev user."""
    if settings.store == "firestore":
        from mojo_picon.store.firestore import FirestoreStore

        return FirestoreStore.connect(project_id=settings.gcp_project_id, database=settings.firestore_database)
    store = InMemoryStore()
    for uid in uids:
        asyncio.run(store.save_profile(UserContext(uid=uid), DEMO_PROFILE))
    return store
