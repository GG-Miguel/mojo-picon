"""Domain models (Pydantic). No dependencies on LLMs, FastAPI or MCP (ADR-20)."""

from mojo_picon.domain.food import Allergen, Food, Nutrients
from mojo_picon.domain.plan import Meal, Plan, PlanItem
from mojo_picon.domain.profile import ActivityLevel, Goal, Profile, Sex
from mojo_picon.domain.targets import MacroTargets

__all__ = [
    "ActivityLevel",
    "Allergen",
    "Food",
    "Goal",
    "MacroTargets",
    "Meal",
    "Nutrients",
    "Plan",
    "PlanItem",
    "Profile",
    "Sex",
]
