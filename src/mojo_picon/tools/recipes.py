"""Mis recetas: dishes made of foods of the table, with their nutrients computed by code.

A recipe is a list of ingredients (food_id -> grams of the whole recipe) and a number of servings. Its
nutrients per 100 g and its allergens come from the ingredients in the food table, so the model never
writes a number for a recipe, as with any other food (Principles #1). As a Food, a recipe works with
search, logging, allergen checks and the number checker unchanged; `serving_g` lets the user log
«una ración». The library (data/recipes.yaml) is shared; a user's own recipes are stored with their
products (category «mis_recetas»), only after the user has confirmed the ingredients.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from mojo_picon.domain import Allergen, Food, Nutrients

DEFAULT_RECIPES = Path(__file__).resolve().parents[3] / "data" / "recipes.yaml"
MAX_INGREDIENTS = 20
MAX_SERVINGS = 12
MAX_RECIPE_G = 5000  # a whole recipe for a family; above this the grams are not credible
USER_PREFIX = "mireceta_"
CATEGORY = "recetas"
USER_CATEGORY = "mis_recetas"


class RecipeError(ValueError):
    """The recipe cannot be built or saved; the message says why, for the model and the user."""


class Recipe(BaseModel):
    id: str
    nombre: str
    raciones: int = Field(gt=0, le=MAX_SERVINGS)
    ingredientes: dict[str, float]
    pasos: list[str] = []
    etiquetas: list[str] = []
    validado: bool = False


def to_food(recipe_id: str, name: str, servings: int, ingredients: dict[str, float], foods: dict[str, Food],
            category: str = CATEGORY, source: str = "receta (ingredientes de la tabla)") -> Food:  # fmt: skip
    """The recipe as a Food: nutrients per 100 g and allergens from its ingredients, one serving in grams."""
    if not ingredients:
        raise RecipeError("la receta necesita al menos un ingrediente")
    if len(ingredients) > MAX_INGREDIENTS:
        raise RecipeError(f"como mucho {MAX_INGREDIENTS} ingredientes")
    if not 0 < servings <= MAX_SERVINGS:
        raise RecipeError(f"las raciones deben estar entre 1 y {MAX_SERVINGS}")
    unknown = [f for f in ingredients if f not in foods]
    if unknown:
        raise RecipeError(f"ingredientes que no están en la tabla: {', '.join(unknown)}; búscalos con search_food")
    if any(g <= 0 for g in ingredients.values()):
        raise RecipeError("cada ingrediente necesita una cantidad en gramos mayor que 0")
    total = sum(ingredients.values())
    if total > MAX_RECIPE_G:
        raise RecipeError(f"la receta suma {total:g} g; como mucho {MAX_RECIPE_G} g")
    nutrients = Nutrients.zero()
    allergens: frozenset[Allergen] = frozenset()
    for food_id, grams in ingredients.items():
        nutrients = nutrients + foods[food_id].nutrients_for(grams)
        allergens |= foods[food_id].allergens
    return Food(
        id=recipe_id,
        name=" ".join(name.split())[:60],
        per_100g=nutrients.scaled(100 / total),
        allergens=allergens,
        max_portion_g=total,
        serving_g=round(total / servings, 1),
        category=category,
        source=source,
    )


@lru_cache(maxsize=2)
def _read(path: Path) -> tuple[Recipe, ...]:
    with path.open(encoding="utf-8") as f:
        return tuple(Recipe.model_validate(r) for r in yaml.safe_load(f))


def load_recipes(foods: dict[str, Food], path: Path = DEFAULT_RECIPES) -> dict[str, tuple[Recipe, Food]]:
    """The recipe library: id -> (recipe, its Food). Raises RecipeError if a recipe does not fit the table."""
    out = {}
    for recipe in _read(path):
        if recipe.id in out or recipe.id in foods:
            raise RecipeError(f"id de receta repetido: {recipe.id}")
        out[recipe.id] = (recipe, to_food(recipe.id, recipe.nombre, recipe.raciones, recipe.ingredientes, foods))
    return out


def user_recipe_id(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:40]
    if not slug:
        raise RecipeError("la receta necesita un nombre")
    return USER_PREFIX + slug


def build_user_recipe(name: str, servings: int, ingredients: dict[str, float], foods: dict[str, Food]) -> Food:
    """A user's own recipe as a Food, ready to store with their products."""
    return to_food(user_recipe_id(name), name, servings, ingredients, foods, category=USER_CATEGORY,
                   source="receta del usuario (ingredientes de la tabla)")  # fmt: skip


def matching(recipes: list[tuple[str, str, list[str]]], query: str) -> list[str]:
    """Ids of the recipes (id, name, tags) whose name or tags contain every word of the query."""

    def plain(text: str) -> str:
        return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()

    words = [w for w in re.split(r"\W+", plain(query)) if len(w) > 2]
    hits = []
    for recipe_id, name, tags in recipes:
        text = plain(" ".join([name, *tags]).replace("_", " "))
        if all(w in text for w in words):
            hits.append(recipe_id)
    return hits
