"""Data access. Every method takes the UserContext and only touches `users/{ctx.uid}` (ADR-14).

There is no method that receives a uid from outside: a tool cannot read or write another
user's data even if the model asks for it.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Profile
from mojo_picon.domain.diary import DiaryEntry, Session
from mojo_picon.domain.food import Food


class Store(Protocol):
    async def get_profile(self, ctx: UserContext) -> Profile | None: ...

    async def save_profile(self, ctx: UserContext, profile: Profile) -> None: ...

    async def put_entry(self, ctx: UserContext, day: date, entry: DiaryEntry) -> None:
        """Create or replace an entry by id (idempotent: logging the same id twice does not duplicate)."""
        ...

    async def list_entries(self, ctx: UserContext, day: date) -> list[DiaryEntry]: ...

    async def get_products(self, ctx: UserContext) -> list[Food]: ...

    async def save_product(self, ctx: UserContext, product: Food) -> None: ...

    async def get_session(self, ctx: UserContext, session_id: str) -> Session | None: ...

    async def save_session(self, ctx: UserContext, session: Session) -> None: ...
