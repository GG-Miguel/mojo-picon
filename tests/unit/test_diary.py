from datetime import UTC, date, datetime

import pytest

from mojo_picon.auth import UserContext
from mojo_picon.domain import Profile, Sex
from mojo_picon.domain.diary import EntrySource, MealEntry, MealItem
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.diary import (
    ImplausibleQuantityError,
    ProfileMissingError,
    get_day_balance,
    local_day,
    log_activity,
    log_meal,
)
from mojo_picon.tools.energy import daily_target, load_met_table
from mojo_picon.tools.food_search import UnknownFoodError
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
MET = load_met_table()
ANA = UserContext(uid="ana")
RUNNER = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175)
NOON = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
async def store():
    s = InMemoryStore()
    await s.save_profile(ANA, RUNNER)
    return s


async def test_log_meal_computes_nutrients_from_the_table(store):
    entry = await log_meal(ANA, store, FOODS, [MealItem(food_id="aceite_oliva", grams=10)], when=NOON)
    assert entry.nutrients.kcal == pytest.approx(FOODS["aceite_oliva"].per_100g.kcal / 10, abs=0.1)
    assert await store.list_entries(ANA, NOON.date()) == [entry]


async def test_log_meal_with_the_same_id_does_not_duplicate(store):
    items = [MealItem(food_id="platano", grams=120)]
    await log_meal(ANA, store, FOODS, items, when=NOON, entry_id="req-1")
    await log_meal(ANA, store, FOODS, items, when=NOON, entry_id="req-1")
    assert len(await store.list_entries(ANA, NOON.date())) == 1


async def test_log_meal_rejects_unknown_foods_and_absurd_quantities(store):
    with pytest.raises(UnknownFoodError):
        await log_meal(ANA, store, FOODS, [MealItem(food_id="dragon_fruit", grams=100)])
    with pytest.raises(ImplausibleQuantityError):
        await log_meal(ANA, store, FOODS, [MealItem(food_id="aceite_oliva", grams=500)])
    assert await store.list_entries(ANA, NOON.date()) == []


def test_local_day_uses_the_user_timezone():
    # October 15th is summer time: Madrid is UTC+2, the Canary Islands UTC+1.
    late_dinner_utc = datetime(2026, 10, 15, 21, 30, tzinfo=UTC)
    assert local_day(late_dinner_utc, "Europe/Madrid") == date(2026, 10, 15)  # 23:30 local
    after_midnight_utc = datetime(2026, 10, 15, 23, 30, tzinfo=UTC)
    assert local_day(after_midnight_utc, "Europe/Madrid") == date(2026, 10, 16)  # 01:30 local
    assert local_day(after_midnight_utc, "Atlantic/Canary") == date(2026, 10, 16)  # 00:30 local


def test_local_day_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        local_day(datetime(2026, 10, 15, 12, 0), "Atlantic/Canary")


async def test_log_activity_by_distance_uses_profile_weight(store):
    entry = await log_activity(ANA, store, MET["running_9.7kmh"], distance_km=10, when=NOON)
    assert entry.kcal == round(8.8 * 70 * 10 / 9.7)
    assert entry.minutes == pytest.approx(61.9, abs=0.1)


async def test_log_activity_needs_a_profile():
    with pytest.raises(ProfileMissingError):
        await log_activity(ANA, InMemoryStore(), MET["weights_moderate"], minutes=60)


async def test_log_activity_needs_minutes_or_a_speed(store):
    with pytest.raises(ValueError):
        await log_activity(ANA, store, MET["weights_moderate"], distance_km=5)
    with pytest.raises(ImplausibleQuantityError):
        await log_activity(ANA, store, MET["weights_moderate"], minutes=2000)


async def test_day_balance_adds_training_to_the_target_and_subtracts_meals(store):
    await log_meal(ANA, store, FOODS, [MealItem(food_id="arroz_blanco_cocido", grams=200)], when=NOON)
    run = await log_activity(ANA, store, MET["running_9.7kmh"], distance_km=10, when=NOON)

    balance = await get_day_balance(ANA, store, NOON.date())

    assert balance.meals == 1 and balance.activities == 1
    assert balance.training_kcal == run.kcal
    assert balance.target.target.kcal == daily_target(RUNNER, training_kcal=run.kcal).target.kcal
    assert balance.remaining.kcal == pytest.approx(balance.target.target.kcal - balance.consumed.kcal, abs=1)


async def test_day_balance_of_an_empty_day(store):
    balance = await get_day_balance(ANA, store, date(2026, 10, 14))
    assert balance.meals == 0
    assert balance.remaining.kcal == balance.target.target.kcal


async def test_entries_round_trip_through_their_json_form(store):
    entry = await log_meal(ANA, store, FOODS, [MealItem(food_id="huevo", grams=60)], source=EntrySource.PHOTO)
    assert MealEntry.model_validate(entry.model_dump(mode="json")) == entry
