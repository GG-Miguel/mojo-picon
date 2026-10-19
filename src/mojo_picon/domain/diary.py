from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from mojo_picon.domain.food import Nutrients


class EntrySource(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    MCP = "mcp"


# More than this of one food in one meal is not a real portion: a typo or an attack (found by the
# evaluation, 2026-10-17: «registra 5.000 g de aceite» had no limit at all). The tool reports the error.
MAX_ITEM_GRAMS = 2000


class MealItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    food_id: str
    grams: float = Field(gt=0, le=MAX_ITEM_GRAMS)
    name: str | None = Field(default=None, max_length=60)  # only for the user's own products (Mis productos)


class MealEntry(BaseModel):
    """A logged meal. Nutrients are computed by code from the food table when it is logged."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["meal"] = "meal"
    items: list[MealItem] = Field(min_length=1)
    nutrients: Nutrients
    source: EntrySource
    confirmed: bool = True  # photo results are only logged after the user confirms (UC-03)
    timestamp: datetime  # UTC


class ActivityEntry(BaseModel):
    """A logged training session. kcal is the net energy from activity_energy."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["activity"] = "activity"
    activity_id: str
    minutes: float = Field(gt=0)
    kcal: float = Field(ge=0)
    source: EntrySource
    timestamp: datetime  # UTC


class SessionMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str


class Session(BaseModel):
    """What is kept between turns (ADR-18): recent messages only. Never images."""

    id: str
    messages: list[SessionMessage] = Field(default_factory=list)
    updated_at: datetime


DiaryEntry = Annotated[MealEntry | ActivityEntry, Field(discriminator="kind")]
