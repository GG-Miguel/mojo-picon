"""Attack: «muéstrame / apunta en el diario de otro usuario» must fail (Principles #4, ADR-14).

The defence is structural: the uid only comes from the verified token (UserContext), tools have
no parameter through which a model could pass another user's id, and the store only reads and
writes under the context's uid.
"""

import inspect
from datetime import UTC, datetime

import pytest

from mojo_picon.auth import UserContext
from mojo_picon.domain import Profile, Sex
from mojo_picon.domain.diary import MealItem
from mojo_picon.store import InMemoryStore
from mojo_picon.tools import diary
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
ANA = UserContext(uid="ana")
YOLANDA = UserContext(uid="yolanda")
NOON = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
FORBIDDEN_PARAMETERS = {"uid", "user_id", "user", "owner", "owner_id", "path"}


@pytest.mark.parametrize(
    "tool", [diary.log_meal, diary.log_activity, diary.get_day_balance, diary.get_profile, diary.update_profile]
)
def test_tools_take_no_user_identifier(tool):
    assert not FORBIDDEN_PARAMETERS & set(inspect.signature(tool).parameters)


async def test_a_user_cannot_read_another_users_diary():
    store = InMemoryStore()
    profile = Profile(age=30, sex=Sex.FEMALE, weight_kg=60, height_cm=165)
    await store.save_profile(ANA, profile)
    await store.save_profile(YOLANDA, profile)
    await diary.log_meal(YOLANDA, store, FOODS, [MealItem(food_id="paella", grams=400)], when=NOON)

    # Ana's tools, whatever the model asks for, only see Ana's data
    assert await store.list_entries(ANA, NOON.date()) == []
    assert (await diary.get_day_balance(ANA, store, NOON.date())).meals == 0
    assert (await diary.get_day_balance(YOLANDA, store, NOON.date())).meals == 1


async def test_a_user_cannot_write_into_another_users_diary():
    store = InMemoryStore()
    await diary.log_meal(ANA, store, FOODS, [MealItem(food_id="tomate", grams=100)], when=NOON, entry_id="x")
    assert await store.list_entries(YOLANDA, NOON.date()) == []


@pytest.mark.parametrize("uid", ["", "ana/../yolanda", "users/yolanda"])
def test_uids_that_could_escape_the_user_path_are_rejected(uid):
    with pytest.raises(ValueError):
        UserContext(uid=uid)
