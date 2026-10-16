from __future__ import annotations

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


class VisionResult(BaseModel):
    """Structured output of the vision extractor (Análisis de fotos)."""

    is_food: bool
    items: list[VisionItem] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, description="preguntas generales sobre el plato")

    @field_validator("items")
    @classmethod
    def _few_items(cls, value: list[VisionItem]) -> list[VisionItem]:
        return value[:MAX_ITEMS]

    @field_validator("questions")
    @classmethod
    def _short_questions(cls, value: list[str]) -> list[str]:
        return _cut_questions(value)
