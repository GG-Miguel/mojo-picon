from __future__ import annotations

from pydantic import BaseModel, Field


class VisionItem(BaseModel):
    """A food seen in the photo, as the model estimates it: a range, never a single number."""

    food: str = Field(description="nombre del alimento en español, genérico (p. ej. 'arroz blanco cocido')")
    grams_min: float = Field(ge=0, le=2000)
    grams_max: float = Field(ge=0, le=2000)
    confidence: float = Field(ge=0, le=1)
    questions: list[str] = Field(default_factory=list, description="lo que no se ve: aceite, salsas…")


class VisionResult(BaseModel):
    """Structured output of the vision extractor (Análisis de fotos)."""

    is_food: bool
    items: list[VisionItem] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, description="preguntas generales sobre el plato")
