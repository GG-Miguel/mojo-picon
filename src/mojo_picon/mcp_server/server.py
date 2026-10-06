"""MCP server: a thin adapter over tools/ for external agents (ADR-07, ADR-17, ADR-21).

Only deterministic tools are exposed: logging, querying and calculating. Anything that reasons
(planning the rest of the day) is delegated through A2A, where the Coach and the guardian take
part. The Coach itself does not use this server: it calls tools/ directly.

The user is always the owner of the MCP token: tools have no user parameter (ADR-14).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from fastmcp.server.dependencies import get_access_token
from pydantic import Field

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Food, Nutrients
from mojo_picon.domain.diary import ActivityEntry, EntrySource, MealEntry, MealItem
from mojo_picon.mcp_server.tokens import user_context_from
from mojo_picon.store.base import Store
from mojo_picon.tools import diary
from mojo_picon.tools.energy import MetActivity
from mojo_picon.tools.food_search import FoodIndex, SearchResult, UnknownFoodError, check_allergens, get_nutrients

# request_id becomes a Firestore document id: safe characters only
RequestId = Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]

INSTRUCTIONS = """\
Mojo Picón: nutrition diary tools for the user who owns the token. Food names are in Spanish.
Numbers come from official food composition tables (CIQUAL, BEDCA), never from a model.
Workflow: search_food -> pick a food_id (ask the user if the result is ambiguous) -> log_meal
with grams -> get_day_balance. These tools do not give health advice; to ask Mojo Picón for a
plan or advice, delegate to its A2A agent.
"""


def build_mcp(
    store: Store,
    foods: Mapping[str, Food],
    activities: Mapping[str, MetActivity],
    auth: AuthProvider | None,
    resolve_context: Callable[[], UserContext] | None = None,
) -> FastMCP:
    """`resolve_context` defaults to the owner of the request's token; tests can inject a user."""
    index = FoodIndex(foods)
    mcp = FastMCP("mojo-picon", instructions=INSTRUCTIONS, auth=auth, mask_error_details=True)

    def context() -> UserContext:
        try:
            return resolve_context() if resolve_context else user_context_from(get_access_token())
        except PermissionError as e:
            raise ToolError(str(e)) from e

    async def diary_context() -> UserContext:
        """The caller, with the timezone of their profile: the diary day is the user's local day."""
        ctx = context()
        profile = await store.get_profile(ctx)
        if profile and profile.timezone != ctx.timezone:
            return UserContext(uid=ctx.uid, roles=ctx.roles, timezone=profile.timezone)
        return ctx

    @mcp.tool(annotations={"readOnlyHint": True})
    def search_food(query: str) -> SearchResult:
        """Search the food table by Spanish name (plurals and typos allowed).

        Returns candidates with a confidence and a status: exact (use it), approximate (confirm
        with the user), ambiguous (ask which one) or not_found (do not invent a food).
        """
        context()
        return index.search(query)

    @mcp.tool(name="get_nutrients", annotations={"readOnlyHint": True})
    def get_nutrients_tool(food_id: str, grams: float = 100) -> Nutrients:
        """Nutrients of `grams` of a food from the table (kcal, protein, carbs, fat, sugars, fibre…)."""
        context()
        try:
            return get_nutrients(foods, food_id, grams)
        except (UnknownFoodError, ValueError) as e:
            raise ToolError(f"cannot compute nutrients: {e}") from e

    @mcp.tool(name="check_allergens", annotations={"readOnlyHint": True})
    async def check_allergens_tool(food_ids: list[str]) -> dict[str, list[str]]:
        """Which of these foods contain an allergen of the token owner's profile."""
        ctx = context()
        profile = await _profile(ctx)
        try:
            found = check_allergens(foods, food_ids, profile.allergens)
        except UnknownFoodError as e:
            raise ToolError(f"unknown food: {e}") from e
        return {food_id: sorted(a.value for a in allergens) for food_id, allergens in found.items()}

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_activities() -> list[MetActivity]:
        """Activities that can be logged, with their MET value and speed (for distances)."""
        context()
        return list(activities.values())

    @mcp.tool(annotations={"destructiveHint": False, "idempotentHint": True})
    async def log_meal(items: list[MealItem], request_id: RequestId = None) -> MealEntry:
        """Log a meal the user has confirmed, as food_id + grams (use search_food first).

        Nutrients are computed from the table. Reusing the same request_id does not duplicate it.
        """
        ctx = await diary_context()
        try:
            return await diary.log_meal(ctx, store, foods, items, source=EntrySource.MCP, entry_id=request_id)
        except (UnknownFoodError, diary.ImplausibleQuantityError, ValueError) as e:
            raise ToolError(f"meal not logged: {e}") from e

    @mcp.tool(annotations={"destructiveHint": False, "idempotentHint": True})
    async def log_activity(
        activity_id: str,
        minutes: float | None = None,
        distance_km: float | None = None,
        request_id: RequestId = None,
    ) -> ActivityEntry:
        """Log a training session (see list_activities). Give minutes, or a distance for running."""
        ctx = await diary_context()
        activity = activities.get(activity_id)
        if activity is None:
            raise ToolError(f"unknown activity {activity_id!r}; see list_activities")
        try:
            return await diary.log_activity(
                ctx, store, activity, minutes=minutes, distance_km=distance_km, source=EntrySource.MCP,
                entry_id=request_id,
            )  # fmt: skip
        except diary.ProfileMissingError as e:
            raise ToolError("the user has no profile yet; it is created in the Mojo Picón app") from e
        except (diary.ImplausibleQuantityError, ValueError) as e:
            raise ToolError(f"activity not logged: {e}") from e

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_day_balance(day: date | None = None) -> diary.DayBalance:
        """Target (training included), consumed and remaining for a day (today by default)."""
        ctx = await diary_context()
        try:
            return await diary.get_day_balance(ctx, store, day)
        except diary.ProfileMissingError as e:
            raise ToolError("the user has no profile yet; it is created in the Mojo Picón app") from e

    @mcp.resource("profile://me", mime_type="application/json")
    async def my_profile() -> dict:
        """The token owner's profile (goal, allergies, preferences)."""
        return (await _profile(context())).model_dump(mode="json")

    @mcp.resource("diary://today", mime_type="application/json")
    async def my_diary_today() -> list[dict]:
        """Today's diary entries of the token owner."""
        ctx = await diary_context()
        today = diary.local_day(datetime.now(UTC), ctx.timezone)
        return [e.model_dump(mode="json") for e in await store.list_entries(ctx, today)]

    @mcp.prompt
    def resumen_de_mi_semana() -> str:
        """Summarise the last 7 days with the user's own data (run by the client's model)."""
        return (
            "Llama a get_day_balance para cada uno de los últimos 7 días y resume, en español, "
            "cuánto he comido frente a mi objetivo y cuánto he entrenado. Usa solo las cifras que "
            "devuelven las herramientas y no des consejos de salud."
        )

    async def _profile(ctx: UserContext):
        try:
            return await diary.get_profile(ctx, store)
        except diary.ProfileMissingError as e:
            raise ToolError("the user has no profile yet; it is created in the Mojo Picón app") from e

    return mcp
