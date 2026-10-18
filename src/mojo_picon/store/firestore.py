"""Firestore implementation of the Store (database `mojopicon`, europe-west1).

Layout (specs: data model):
    users/{uid}/profile/current
    users/{uid}/days/{YYYY-MM-DD}/entries/{entry_id}
    users/{uid}/sessions/{session_id}
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Goal, Profile
from mojo_picon.domain.diary import DiaryEntry, Session
from mojo_picon.domain.profile import MAX_WEEKLY_GAIN_KG

if TYPE_CHECKING:
    from google.cloud.firestore import AsyncClient, AsyncDocumentReference

DEFAULT_DATABASE = "mojopicon"
_ENTRY = TypeAdapter(DiaryEntry)


class FirestoreStore:
    def __init__(self, client: AsyncClient):
        self._db = client

    @classmethod
    def connect(cls, project_id: str, database: str = DEFAULT_DATABASE) -> FirestoreStore:
        """Uses Application Default Credentials, or the emulator if FIRESTORE_EMULATOR_HOST is set."""
        from google.cloud.firestore import AsyncClient

        return cls(AsyncClient(project=project_id, database=database))

    def _user(self, ctx: UserContext) -> AsyncDocumentReference:
        return self._db.collection("users").document(ctx.uid)

    async def get_profile(self, ctx: UserContext) -> Profile | None:
        snapshot = await self._user(ctx).collection("profile").document("current").get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("goal") == Goal.GAIN and data.get("weekly_rate_kg", 0) > MAX_WEEKLY_GAIN_KG:
            data["weekly_rate_kg"] = MAX_WEEKLY_GAIN_KG  # saved before the gain limit existed
        return Profile.model_validate(data)

    async def save_profile(self, ctx: UserContext, profile: Profile) -> None:
        await self._user(ctx).collection("profile").document("current").set(profile.model_dump(mode="json"))

    async def put_entry(self, ctx: UserContext, day: date, entry: DiaryEntry) -> None:
        ref = self._user(ctx).collection("days").document(day.isoformat()).collection("entries").document(entry.id)
        await ref.set(entry.model_dump(mode="json"))

    async def list_entries(self, ctx: UserContext, day: date) -> list[DiaryEntry]:
        entries = self._user(ctx).collection("days").document(day.isoformat()).collection("entries")
        found = [_ENTRY.validate_python(snapshot.to_dict()) async for snapshot in entries.stream()]
        return sorted(found, key=lambda e: e.timestamp)

    async def get_session(self, ctx: UserContext, session_id: str) -> Session | None:
        snapshot = await self._user(ctx).collection("sessions").document(session_id).get()
        return Session.model_validate(snapshot.to_dict()) if snapshot.exists else None

    async def save_session(self, ctx: UserContext, session: Session) -> None:
        await self._user(ctx).collection("sessions").document(session.id).set(session.model_dump(mode="json"))
