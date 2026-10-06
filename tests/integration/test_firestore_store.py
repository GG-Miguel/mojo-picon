"""FirestoreStore against the Firestore emulator. Skipped unless FIRESTORE_EMULATOR_HOST is set.

docker compose up firestore   # or: gcloud emulators firestore start
FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest -m integration
"""

import os
import uuid
from datetime import UTC, datetime

import pytest

from mojo_picon.auth import UserContext
from mojo_picon.domain import Profile, Sex
from mojo_picon.domain.diary import MealItem
from mojo_picon.store.firestore import FirestoreStore
from mojo_picon.tools import diary
from mojo_picon.tools.foods import load_foods

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="Firestore emulator not running"),
]

NOON = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def store():
    return FirestoreStore.connect(project_id="demo-mojo-picon")


@pytest.fixture
def users():
    run = uuid.uuid4().hex[:8]  # fresh users on every run; the emulator keeps data between runs
    return UserContext(uid=f"ana-{run}"), UserContext(uid=f"yolanda-{run}")


async def test_profile_round_trip(store, users):
    ana, _ = users
    profile = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175)
    assert await store.get_profile(ana) is None
    await store.save_profile(ana, profile)
    assert await store.get_profile(ana) == profile


async def test_entries_are_idempotent_and_isolated_per_user(store, users):
    ana, yolanda = users
    items = [MealItem(food_id="gofio", grams=30)]
    first = await diary.log_meal(ana, store, load_foods(), items, when=NOON, entry_id="req-1")
    await diary.log_meal(ana, store, load_foods(), items, when=NOON, entry_id="req-1")

    assert await store.list_entries(ana, NOON.date()) == [first]
    assert await store.list_entries(yolanda, NOON.date()) == []
