"""Pre-load the demo user: profile and today's breakfast, so the demo starts mid-day (Tareas Hito 1).

The user is the Firebase account used in the demo (it must have signed in once). Idempotent: the
breakfast has a fixed id per day, so running it twice does not duplicate it.

    uv run python scripts/seed_demo_user.py --email you@example.com            # Firestore
    uv run python scripts/seed_demo_user.py --email you@example.com --dry-run  # only print
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from mojo_picon.auth.context import UserContext
from mojo_picon.config import Settings
from mojo_picon.domain import ActivityLevel, Goal, Profile, Sex
from mojo_picon.domain.diary import MealItem
from mojo_picon.store.base import Store
from mojo_picon.tools import diary
from mojo_picon.tools.foods import load_foods

# Demo persona (Resumen del proyecto: usuario tipo): an adult who runs and wants to eat sensibly
DEMO_PROFILE = Profile(
    age=34,
    sex=Sex.MALE,
    weight_kg=72,
    height_cm=176,
    activity_level=ActivityLevel.LIGHT,
    goal=Goal.MAINTAIN,
    timezone="Atlantic/Canary",
)
BREAKFAST = [
    MealItem(food_id="pan_tostado_casero", grams=60),
    MealItem(food_id="aceite_oliva", grams=10),
    MealItem(food_id="cafe_con_leche", grams=200),
]


async def seed(store: Store, user: UserContext, day: date) -> None:
    await diary.update_profile(user, store, DEMO_PROFILE)
    breakfast_at = datetime.combine(day, time(8, 30), tzinfo=ZoneInfo(DEMO_PROFILE.timezone)).astimezone(UTC)
    await diary.log_meal(
        UserContext(uid=user.uid, timezone=DEMO_PROFILE.timezone),
        store,
        load_foods(),
        BREAKFAST,
        when=breakfast_at,
        entry_id=f"demo-breakfast-{day.isoformat()}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Google account used in the demo")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="day to pre-load (default: today)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    day = args.date or datetime.now(ZoneInfo(DEMO_PROFILE.timezone)).date()

    import firebase_admin
    from firebase_admin import auth

    firebase_admin.initialize_app(options={"projectId": settings.gcp_project_id})
    uid = auth.get_user_by_email(args.email).uid
    print(f"Demo user {args.email} -> uid {uid[:6]}…; day {day}; breakfast {[i.food_id for i in BREAKFAST]}")
    if args.dry_run:
        return
    from mojo_picon.store.firestore import FirestoreStore

    store = FirestoreStore.connect(project_id=settings.gcp_project_id, database=settings.firestore_database)
    asyncio.run(seed(store, UserContext(uid=uid), day))
    print("Done.")


if __name__ == "__main__":
    main()
