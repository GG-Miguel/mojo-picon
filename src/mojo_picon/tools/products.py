"""Mis productos: foods of one user, read from the nutrition label of a package (photo, then confirmed).

A product is a Food with id «mi_<name>» in `users/{uid}/products`. The values come from the label as
the vision model read it and the user confirmed it; before saving, the code checks that the kcal fit
the macronutrients (4/4/9), which catches a misread figure. Products are for logging only: their
allergens are unknown, so the planner never proposes them.
"""

from __future__ import annotations

import re
import unicodedata

from mojo_picon.auth.context import UserContext
from mojo_picon.domain.food import Food, Nutrients
from mojo_picon.store.base import Store

PREFIX = "mi_"
MAX_PRODUCTS = 200  # per user: nothing without a limit
SODIUM_MG_PER_G_SALT = 400  # EU Regulation 1169/2011: salt = sodium x 2.5
# Labels round each value, fibre adds ~2 kcal/g and polyols or alcohol others: a wide tolerance, enough
# to catch a misread digit (e.g. 45 g of fat read as 4.5 g)
KCAL_TOLERANCE = 0.20
KCAL_TOLERANCE_ABS = 25


class ProductError(ValueError):
    """The product cannot be saved; the message says why, for the model and the user."""


def product_id(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:50]
    if not slug:
        raise ProductError("el producto necesita un nombre")
    return PREFIX + slug


def check_energy(kcal: float, protein_g: float, carbs_g: float, fat_g: float, fiber_g: float = 0) -> None:
    expected = 4 * protein_g + 4 * carbs_g + 9 * fat_g + 2 * fiber_g
    if abs(kcal - expected) > max(KCAL_TOLERANCE * expected, KCAL_TOLERANCE_ABS):
        raise ProductError(
            f"las kcal ({kcal:g}) no cuadran con los macronutrientes (≈ {expected:.0f} kcal): "
            "comprueba con el usuario la lectura de la etiqueta"
        )


async def save_product(
    ctx: UserContext,
    store: Store,
    name: str,
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    sugars_g: float = 0,
    saturated_g: float = 0,
    fiber_g: float = 0,
    salt_g: float = 0,
) -> Food:
    check_energy(kcal, protein_g, carbs_g, fat_g, fiber_g)
    if sugars_g > carbs_g or saturated_g > fat_g:
        raise ProductError("los azúcares no pueden superar los hidratos ni las saturadas las grasas")
    existing = {p.id for p in await store.get_products(ctx)}
    food_id = product_id(name)
    if food_id not in existing and len(existing) >= MAX_PRODUCTS:
        raise ProductError(f"ya tienes {MAX_PRODUCTS} productos guardados")
    product = Food(
        id=food_id,
        name=" ".join(name.split())[:60],
        per_100g=Nutrients(
            kcal=kcal,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            sugars_g=sugars_g,
            saturated_g=saturated_g,
            fiber_g=fiber_g,
            sodium_mg=salt_g * SODIUM_MG_PER_G_SALT,
        ),
        category="mis_productos",
        source="etiqueta del envase (usuario)",
    )
    await store.save_product(ctx, product)
    return product


def matching(products: list[Food], query: str) -> list[Food]:
    """The user's products whose name contains every word of the query (accents and case ignored)."""

    def plain(text: str) -> str:
        return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()

    words = [w for w in re.split(r"\W+", plain(query)) if len(w) > 2]
    return [p for p in products if words and all(w in plain(p.name) for w in words)]
