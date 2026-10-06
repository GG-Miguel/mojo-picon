from __future__ import annotations

from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mojo_picon.domain.food import Allergen


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class ActivityLevel(StrEnum):
    """Daily life activity, **excluding training**.

    Training sessions are logged separately and added with `activity_energy`, so they are
    not counted twice (once in the factor and once as logged activity).
    """

    SEDENTARY = "sedentary"  # desk job, little walking
    LIGHT = "light"  # some walking or standing
    MODERATE = "moderate"  # on your feet most of the day
    HIGH = "high"  # physical job


class Goal(StrEnum):
    MAINTAIN = "maintain"
    LOSE = "lose"
    GAIN = "gain"


MAX_WEEKLY_RATE_KG = 1.0  # faster weight change is an extreme goal (Decisiones pendientes #5)


class Profile(BaseModel):
    model_config = ConfigDict(frozen=True)

    age: int = Field(ge=18, le=100)  # minors are referred to a professional (Guardrails)
    sex: Sex
    weight_kg: float = Field(gt=30, lt=300)
    height_cm: float = Field(gt=120, lt=250)
    activity_level: ActivityLevel = ActivityLevel.LIGHT
    goal: Goal = Goal.MAINTAIN
    weekly_rate_kg: float = Field(default=0.5, ge=0, le=MAX_WEEKLY_RATE_KG)  # only when losing or gaining
    allergens: frozenset[Allergen] = frozenset()
    timezone: str = "Atlantic/Canary"

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone {value!r}") from e
        return value
