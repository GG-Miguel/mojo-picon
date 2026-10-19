from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Nothing without a limit (Principles), and a defence against text written in the photo
# (OWASP LLM01, indirect injection): whatever the model copies from the image cannot grow into
# an instruction-sized text. Longer values are cut, not rejected, so a photo is never lost.
MAX_FOOD_CHARS = 60
MAX_QUESTION_CHARS = 120
MAX_QUESTIONS = 3
MAX_ITEMS = 10


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _cut_questions(questions: list[str]) -> list[str]:
    return [_cut(q, MAX_QUESTION_CHARS) for q in questions if q.strip()][:MAX_QUESTIONS]


class VisionItem(BaseModel):
    """A food seen in the photo, as the model estimates it: a range, never a single number."""

    food: str = Field(description="nombre del alimento en español, genérico (p. ej. 'arroz blanco cocido')")
    grams_min: float = Field(ge=0, le=2000)
    grams_max: float = Field(ge=0, le=2000)
    confidence: float = Field(ge=0, le=1)
    questions: list[str] = Field(default_factory=list, description="lo que no se ve: aceite, salsas…")

    @field_validator("food")
    @classmethod
    def _short_food(cls, value: str) -> str:
        return _cut(value, MAX_FOOD_CHARS)

    @field_validator("questions")
    @classmethod
    def _short_questions(cls, value: list[str]) -> list[str]:
        return _cut_questions(value)


class NutritionLabel(BaseModel):
    """The nutrition table of a package, copied from the photo (Mis productos). Values per 100 g or ml,
    as printed: the user confirms them and save_product checks that kcal fit the macronutrients."""

    product: str = Field(description="nombre del producto tal como aparece en el envase (marca y tipo)")
    basis: Literal["100 g", "100 ml"] = "100 g"
    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    sugars_g: float = Field(default=0, ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    saturated_g: float = Field(default=0, ge=0, le=100)
    fiber_g: float = Field(default=0, ge=0, le=100)
    salt_g: float = Field(default=0, ge=0, le=100)
    serving_g: float | None = Field(default=None, gt=0, le=2000, description="ración del envase, si la indica")

    @field_validator("product")
    @classmethod
    def _short_product(cls, value: str) -> str:
        return _cut(value, MAX_FOOD_CHARS)


class VisionResult(BaseModel):
    """Structured output of the vision extractor (Análisis de fotos)."""

    is_food: bool
    items: list[VisionItem] = Field(default_factory=list)
    label: NutritionLabel | None = Field(default=None, description="solo si la foto es una tabla nutricional")
    questions: list[str] = Field(default_factory=list, description="preguntas generales sobre el plato")

    @field_validator("items")
    @classmethod
    def _few_items(cls, value: list[VisionItem]) -> list[VisionItem]:
        return value[:MAX_ITEMS]

    @field_validator("questions")
    @classmethod
    def _short_questions(cls, value: list[str]) -> list[str]:
        return _cut_questions(value)
