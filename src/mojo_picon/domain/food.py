from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Allergen(StrEnum):
    """The 14 allergens of EU Regulation 1169/2011, Annex II."""

    GLUTEN = "gluten"
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    SOY = "soy"
    MILK = "milk"
    TREE_NUTS = "tree_nuts"
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SULPHITES = "sulphites"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"


class Nutrients(BaseModel):
    """Nutrients of an amount of food. In `Food`, per 100 g of edible portion."""

    model_config = ConfigDict(frozen=True)

    kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    sugars_g: float = Field(default=0, ge=0)
    saturated_g: float = Field(default=0, ge=0)
    fiber_g: float = Field(default=0, ge=0)
    sodium_mg: float = Field(default=0, ge=0)

    def scaled(self, factor: float) -> Nutrients:
        return Nutrients(**{name: value * factor for name, value in self.model_dump().items()})

    def __add__(self, other: Nutrients) -> Nutrients:
        return Nutrients(**{name: value + getattr(other, name) for name, value in self.model_dump().items()})

    @classmethod
    def zero(cls) -> Nutrients:
        return cls(kcal=0, protein_g=0, carbs_g=0, fat_g=0)


class Food(BaseModel):
    """A row of the curated food table (see data/DATASHEET.md)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    per_100g: Nutrients
    allergens: frozenset[Allergen] = frozenset()
    max_portion_g: float = Field(default=500, gt=0)  # above this, a planned quantity is unrealistic
    category: str = ""
    section: str = ""  # supermarket section, for the shopping list
    synonyms: tuple[str, ...] = ()
    source: str = ""  # e.g. "CIQUAL 2020", "recipe", "approximation of bacalao"

    def nutrients_for(self, grams: float) -> Nutrients:
        return self.per_100g.scaled(grams / 100)
