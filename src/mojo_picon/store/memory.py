"""In-memory Store for unit tests and local experiments. Same behaviour as FirestoreStore."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Profile
from mojo_picon.domain.diary import DiaryEntry, Session
from mojo_picon.domain.food import Food


class InMemoryStore:
    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._entries: dict[tuple[str, date], dict[str, DiaryEntry]] = defaultdict(dict)
        self._sessions: dict[tuple[str, str], Session] = {}
        self._products: dict[str, dict[str, Food]] = defaultdict(dict)

    async def get_profile(self, ctx: UserContext) -> Profile | None:
        return self._profiles.get(ctx.uid)

    async def save_profile(self, ctx: UserContext, profile: Profile) -> None:
        self._profiles[ctx.uid] = profile

    async def put_entry(self, ctx: UserContext, day: date, entry: DiaryEntry) -> None:
        self._entries[(ctx.uid, day)][entry.id] = entry

    async def list_entries(self, ctx: UserContext, day: date) -> list[DiaryEntry]:
        return sorted(self._entries[(ctx.uid, day)].values(), key=lambda e: e.timestamp)

    async def get_products(self, ctx: UserContext) -> list[Food]:
        return sorted(self._products[ctx.uid].values(), key=lambda p: p.name)

    async def save_product(self, ctx: UserContext, product: Food) -> None:
        self._products[ctx.uid][product.id] = product

    async def get_session(self, ctx: UserContext, session_id: str) -> Session | None:
        return self._sessions.get((ctx.uid, session_id))

    async def save_session(self, ctx: UserContext, session: Session) -> None:
        self._sessions[(ctx.uid, session.id)] = session
