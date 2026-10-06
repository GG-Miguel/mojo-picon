"""Diary tools: log meals and activity, and the day's balance.

Every function takes the UserContext (injected by the backend, never written by the model) and
a Store that only touches that user's data (ADR-14). All numbers are computed here from the food
table, the MET table and the profile (Principles #1).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Food, MacroTargets, Nutrients, Profile
from mojo_picon.domain.diary import ActivityEntry, EntrySource, MealEntry, MealItem
from mojo_picon.store.base import Store
from mojo_picon.tools.energy import (
    DailyTarget,
    MetActivity,
    activity_energy,
    daily_balance,
    daily_target,
    minutes_for_distance,
)
from mojo_picon.tools.food_search import UnknownFoodError

# Logging accepts more than a planned portion (people do eat big plates), but not absurd amounts.
MAX_LOGGED_PORTION_FACTOR = 3
MAX_ACTIVITY_MINUTES = 600


class ProfileMissingError(LookupError):
    """The user has no profile yet: the agent asks for the missing data (UC-01)."""


class ImplausibleQuantityError(ValueError):
    """A quantity outside plausible limits: the agent asks the user again."""


@dataclass(frozen=True)
class DayBalance:
    day: date
    target: DailyTarget  # includes the logged training
    consumed: Nutrients
    training_kcal: float
    remaining: MacroTargets
    meals: int
    activities: int


def local_day(when: datetime, timezone: str) -> date:
    """The diary day in the user's timezone (a dinner at 23:30 belongs to that day)."""
    if when.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return when.astimezone(ZoneInfo(timezone)).date()


async def get_profile(ctx: UserContext, store: Store) -> Profile:
    profile = await store.get_profile(ctx)
    if profile is None:
        raise ProfileMissingError(ctx.uid)
    return profile


async def update_profile(ctx: UserContext, store: Store, profile: Profile) -> Profile:
    await store.save_profile(ctx, profile)
    return profile


async def log_meal(
    ctx: UserContext,
    store: Store,
    foods: Mapping[str, Food],
    items: list[MealItem],
    source: EntrySource = EntrySource.TEXT,
    when: datetime | None = None,
    entry_id: str | None = None,
) -> MealEntry:
    """Log a meal the user has confirmed. Nutrients are computed from the food table.

    Meals detected in a photo are kept as a pending action in the session and only reach this
    function after the user confirms (UC-03, ADR-18). Passing the same `entry_id` twice does not
    duplicate the meal.
    """
    if not items:
        raise ValueError("a meal needs at least one item")
    total = Nutrients.zero()
    for item in items:
        food = foods.get(item.food_id)
        if food is None:
            raise UnknownFoodError(item.food_id)
        limit = food.max_portion_g * MAX_LOGGED_PORTION_FACTOR
        if item.grams > limit:
            raise ImplausibleQuantityError(f"{food.name}: {item.grams:g} g (limit {limit:g} g)")
        total = total + food.nutrients_for(item.grams)

    when = when or datetime.now(UTC)
    entry = MealEntry(
        id=entry_id or uuid.uuid4().hex,
        items=items,
        nutrients=_rounded(total),
        source=source,
        timestamp=when.astimezone(UTC),
    )
    await store.put_entry(ctx, local_day(when, ctx.timezone), entry)
    return entry


async def log_activity(
    ctx: UserContext,
    store: Store,
    activity: MetActivity,
    minutes: float | None = None,
    distance_km: float | None = None,
    source: EntrySource = EntrySource.TEXT,
    when: datetime | None = None,
    entry_id: str | None = None,
) -> ActivityEntry:
    """Log a training session with its net energy (MET tables and the profile's weight, UC-04).

    Give `minutes`, or `distance_km` for activities with a speed in the MET table («corro 10 km»).
    """
    if minutes is None:
        if distance_km is None or activity.speed_kmh is None:
            raise ValueError("give minutes, or a distance for an activity with a known speed")
        minutes = minutes_for_distance(distance_km, activity.speed_kmh)
    if not 0 < minutes <= MAX_ACTIVITY_MINUTES:
        raise ImplausibleQuantityError(f"{minutes:g} minutes")
    profile = await get_profile(ctx, store)

    when = when or datetime.now(UTC)
    entry = ActivityEntry(
        id=entry_id or uuid.uuid4().hex,
        activity_id=activity.id,
        minutes=round(minutes, 1),
        kcal=activity_energy(activity.met, profile.weight_kg, minutes),
        source=source,
        timestamp=when.astimezone(UTC),
    )
    await store.put_entry(ctx, local_day(when, ctx.timezone), entry)
    return entry


async def get_day_balance(ctx: UserContext, store: Store, day: date | None = None) -> DayBalance:
    """Target, consumed and remaining for a day (today in the user's timezone by default)."""
    profile = await get_profile(ctx, store)
    day = day or local_day(datetime.now(UTC), ctx.timezone)
    entries = await store.list_entries(ctx, day)
    meals = [e for e in entries if isinstance(e, MealEntry)]
    activities = [e for e in entries if isinstance(e, ActivityEntry)]

    consumed = Nutrients.zero()
    for meal in meals:
        consumed = consumed + meal.nutrients
    training_kcal = sum(a.kcal for a in activities)
    target = daily_target(profile, training_kcal=training_kcal)
    return DayBalance(
        day=day,
        target=target,
        consumed=_rounded(consumed),
        training_kcal=training_kcal,
        remaining=daily_balance(target.target, consumed),
        meals=len(meals),
        activities=len(activities),
    )


def _rounded(n: Nutrients) -> Nutrients:
    return Nutrients(**{name: round(value, 1) for name, value in n.model_dump().items()})
