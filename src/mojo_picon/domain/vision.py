from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mojo_picon.domain.food import Allergen
from mojo_picon.vision.allergens import find

# Nothing without a limit (Principles), and a defence against text written in the photo
# (OWASP LLM01, indirect injection): whatever the model copies from the image cannot grow into
# an instruction-sized text. Longer values are cut, not rejected, so a photo is never lost.
MAX_FOOD_CHARS = 60
MAX_QUESTION_CHARS = 120
MAX_QUESTIONS = 3
MAX_ITEMS = 10
MAX_INGREDIENTS = 40
# The photo analysis travels at the end of the user's message between these tags (vision/extractor.py);
# the API neutralises them in the user's own words, so only the analysis can carry them.
PHOTO_OPEN, PHOTO_CLOSE = "<datos_foto>", "</datos_foto>"
_IDS = frozenset(a.value for a in Allergen)
ALLERGEN_IDS = ", ".join(sorted(_IDS))


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


# Package fields the model must always return, empty when the photo is not a package. As an optional
# nested object, Gemini 3.8 Flash (through LiteLLM) filled the ingredients in 1 of 5 runs; as required
# lists, in 6 of 6 (22 Oct). The code keeps defaults, so a result can be built without them.
PACKAGE_FIELDS = ("product", "ingredients", "allergens", "may_contain")


def _require_package_fields(schema: dict) -> None:
    schema["required"] = [*schema.get("required", []), *PACKAGE_FIELDS]


class VisionResult(BaseModel):
    """Structured output of the vision extractor (Análisis de fotos)."""

    model_config = ConfigDict(json_schema_extra=_require_package_fields)

    is_food: bool
    items: list[VisionItem] = Field(default_factory=list)
    label: NutritionLabel | None = Field(default=None, description="solo si la foto es una tabla nutricional")
    product: str = Field(default="", description="nombre del producto del envase; vacío si no es un envase")
    ingredients: list[str] = Field(
        default_factory=list, description="ingredientes del envase, copiados tal cual y en orden; vacía si no se ven"
    )
    # Strings, not list[Allergen]: the validator turns ids or Spanish names («leche», «frutos de cáscara»)
    # into the 14 ids, and the code checks the ingredients again by keyword (vision/allergens.py).
    allergens: list[str] = Field(
        default_factory=list, description=f"alérgenos que contiene según los ingredientes ({ALLERGEN_IDS})"
    )
    may_contain: list[str] = Field(
        default_factory=list, description=f"alérgenos de «puede contener» o «trazas» ({ALLERGEN_IDS})"
    )
    questions: list[str] = Field(default_factory=list, description="preguntas generales sobre el plato")

    @property
    def is_package(self) -> bool:
        return self.label is not None or bool(self.ingredients)

    @field_validator("items")
    @classmethod
    def _few_items(cls, value: list[VisionItem]) -> list[VisionItem]:
        return value[:MAX_ITEMS]

    @field_validator("product")
    @classmethod
    def _short_product(cls, value: str) -> str:
        return _cut(value, MAX_FOOD_CHARS) if value.strip() else ""

    @field_validator("ingredients")
    @classmethod
    def _short_ingredients(cls, value: list[str]) -> list[str]:
        return [_cut(i, MAX_FOOD_CHARS) for i in value if i.strip()][:MAX_INGREDIENTS]

    @field_validator("allergens", "may_contain")
    @classmethod
    def _allergen_ids(cls, value: list[str]) -> list[str]:
        ids: set[str] = set()
        for name in value:
            ids |= {name} if name in _IDS else {a.value for a in find(name)}
        return sorted(ids)

    @field_validator("questions")
    @classmethod
    def _short_questions(cls, value: list[str]) -> list[str]:
        return _cut_questions(value)
