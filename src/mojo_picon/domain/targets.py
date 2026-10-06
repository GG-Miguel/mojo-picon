from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MacroTargets(BaseModel):
    """Energy and macronutrient amounts: a daily target, what is consumed or what remains."""

    model_config = ConfigDict(frozen=True)

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
