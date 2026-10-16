import importlib.util
import sys
from datetime import date
from pathlib import Path

from mojo_picon.auth import UserContext
from mojo_picon.store import InMemoryStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_demo_user.py"


def load():
    spec = importlib.util.spec_from_file_location("seed_demo_user", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_seed_is_idempotent_and_on_the_users_local_day():
    seed = load()
    store, user, day = InMemoryStore(), UserContext(uid="demo"), date(2026, 10, 15)
    await seed.seed(store, user, day)
    await seed.seed(store, user, day)
    entries = await store.list_entries(user, day)
    assert len(entries) == 1
    assert [i.food_id for i in entries[0].items] == ["pan_tostado_casero", "aceite_oliva", "cafe_con_leche"]
    assert await store.get_profile(user) == seed.DEMO_PROFILE
