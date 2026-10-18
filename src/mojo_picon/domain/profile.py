from __future__ import annotations

from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# Faster weight change is an extreme goal. Losing: about 0.5-1 kg per week (consenso FESNAD-SEEDO,
# Nutr Hosp 2012;27(3):833-864). Gaining: about 0.5 kg of muscle per week (Urdampilleta et al.,
# Rev Esp Nutr Hum Diet 2012;16(1):25-35); faster gain is mostly fat.
MAX_WEEKLY_LOSS_KG = 1.0
MAX_WEEKLY_GAIN_KG = 0.5


class Profile(BaseModel):
    model_config = ConfigDict(frozen=True)

    age: int = Field(ge=18, le=100)  # minors are referred to a professional (Guardrails)
    sex: Sex
    weight_kg: float = Field(gt=30, lt=300)
    height_cm: float = Field(gt=120, lt=250)
    activity_level: ActivityLevel = ActivityLevel.LIGHT
    goal: Goal = Goal.MAINTAIN
    weekly_rate_kg: float = Field(default=0.5, ge=0, le=MAX_WEEKLY_LOSS_KG)  # only when losing or gaining
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

    @model_validator(mode="after")
    def _gain_rate(self) -> Profile:
        if self.goal is Goal.GAIN and self.weekly_rate_kg > MAX_WEEKLY_GAIN_KG:
            raise ValueError(f"gaining more than {MAX_WEEKLY_GAIN_KG:g} kg per week is an extreme goal")
        return self
