"""Household measures (cucharada, unidad, vaso, loncha…) -> grams of edible portion, computed by code.

Users say «una cucharada de aceite» or «dos manzanas», not grams. Asking every time is friction, and
these measures have standard weights: data/household_measures.csv takes them from the annex of household
measures of Carbajal (UCM, 2015) and, for foods with peel, bone or shell, multiplies them by the edible
portion of BEDCA, because the food table gives nutrients per 100 g of edible portion. The model never
multiplies: it passes the measure and the count, and this module returns the grams.
"""

from __future__ import annotations

import csv
import unicodedata
from functools import lru_cache
from pathlib import Path

DEFAULT_MEASURES = Path(__file__).resolve().parents[3] / "data" / "household_measures.csv"
MAX_COUNT = 20  # «30 manzanas» is not one meal: the tool reports it, as with grams

# What users say -> the measure names of the table
SYNONYMS = {
    "cuchara": "cucharada",
    "cucharada sopera": "cucharada",
    "cucharada rasa": "cucharada",
    "cucharada grande": "cucharada colmada",
    "cucharilla": "cucharadita",
    "cucharada pequena": "cucharadita",
    "cucharada de postre": "cucharadita",
    "cucharadita de cafe": "cucharadita",
    "pieza": "unidad",
    "unidad mediana": "unidad",
    "mediana": "unidad",
    "mediano": "unidad",
    "pieza mediana": "unidad",
    "pieza pequena": "unidad pequena",
    "pieza grande": "unidad grande",
    "pequena": "unidad pequena",
    "pequeno": "unidad pequena",
    "grande": "unidad grande",
    "loncha fina": "loncha",
    "lonchita": "loncha",
    "rebanadita": "rebanada",
    "tostada": "rebanada",
    "vasito": "vaso",
    "copa": "copa",
    "botella pequena": "botellin",
    "pellizco": "pizca",
}


class UnknownMeasureError(ValueError):
    """The food has no standard weight for that measure: the model asks the user for grams."""

    def __init__(self, food_id: str, measure: str, available: list[str]):
        names = ", ".join(available) or "ninguna"
        super().__init__(f"{food_id} no tiene medida «{measure}»; medidas disponibles: {names}")
        self.available = available


def _key(text: str) -> str:
    """Lowercase, no accents, no plural: «Cucharadas» -> «cucharada», «cañas» -> «cana»."""
    plain = unicodedata.normalize("NFKD", text.strip().lower()).encode("ascii", "ignore").decode()
    words = [w[:-2] if w.endswith("es") and w[:-2].endswith(("d", "l", "n", "r")) else w for w in plain.split()]
    words = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    return " ".join(words)


@lru_cache(maxsize=4)
def load_measures(path: Path = DEFAULT_MEASURES) -> dict[str, dict[str, float]]:
    """food_id -> {measure name: grams of edible portion}."""
    table: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            table.setdefault(row["food_id"], {})[row["measure"]] = float(row["grams"])
    return table


def measures_of(food_id: str, measures: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    return dict((load_measures() if measures is None else measures).get(food_id, {}))


Measures = dict[str, dict[str, float]]


def to_grams(food_id: str, measure: str, count: float = 1, measures: Measures | None = None) -> float:
    """Grams of `count` × `measure` of a food. Raises ValueError for a count out of range and
    UnknownMeasureError if the food has no standard weight for that measure."""
    if not 0 < count <= MAX_COUNT:
        raise ValueError(f"la cantidad debe estar entre 0 y {MAX_COUNT} (recibido {count:g})")
    available = measures_of(food_id, measures)
    by_key = {_key(name): grams for name, grams in available.items()}
    key = _key(measure)
    key = _key(SYNONYMS.get(key, key))
    if key not in by_key:
        raise UnknownMeasureError(food_id, measure, sorted(available))
    return round(by_key[key] * count, 1)
