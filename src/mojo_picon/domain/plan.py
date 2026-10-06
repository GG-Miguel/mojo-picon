from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlanItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    food_id: str
    grams: float = Field(gt=0)


class Meal(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str  # e.g. "merienda", "cena"
    items: list[PlanItem] = Field(min_length=1)


class Plan(BaseModel):
    """Structured output of the Planner: meals for the rest of the day."""

    model_config = ConfigDict(frozen=True)

    meals: list[Meal] = Field(min_length=1)

    @property
    def items(self) -> list[PlanItem]:
        return [item for meal in self.meals for item in meal.items]
