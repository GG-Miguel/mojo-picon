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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_MEASURES = Path(__file__).resolve().parents[3] / "data" / "household_measures.csv"
DEFAULT_DEFINITIONS = Path(__file__).resolve().parents[3] / "data" / "household_measure_definitions.csv"
MAX_COUNT = 20  # «30 manzanas» is not one meal: the tool reports it, as with grams

# What users say -> the measure names of the table
SYNONYMS = {
    "cuchara": "cucharada",
    "cucharada sopera": "cucharada",
    "cuchara sopera": "cucharada",
    "cucharada rasa": "cucharada",
    "cucharada grande": "cucharada colmada",
    "cucharilla": "cucharadita",
    "cuchara de cafe": "cucharadita",
    "cucharada de cafe": "cucharadita",
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
    "plato estandar": "plato",
    "plato llano": "plato",
    "plato hondo": "plato",
    "copa": "copa",
    "botella pequena": "botellin",
    "pellizco": "pizca",
}


@dataclass(frozen=True)
class MeasureDefinition:
    """Canonical conversational measure, independent of an ingredient's density."""

    measure_id: str
    display_name: str
    aliases: tuple[str, ...]
    volume_ml: float | None
    kind: str
    status: str
    source: str


@lru_cache(maxsize=1)
def load_measure_definitions(path: Path = DEFAULT_DEFINITIONS) -> dict[str, MeasureDefinition]:
    """Load canonical names and aliases used by the conversation layer."""
    with path.open(encoding="utf-8") as f:
        return {
            row["measure_id"]: MeasureDefinition(
                measure_id=row["measure_id"],
                display_name=row["display_name"],
                aliases=tuple(alias for alias in row["aliases"].split("|") if alias),
                volume_ml=float(row["volume_ml"]) if row["volume_ml"] else None,
                kind=row["kind"],
                status=row["status"],
                source=row["source"],
            )
            for row in csv.DictReader(f)
        }


_STORAGE_TO_CANONICAL = {
    "cucharada": "cucharada_sopera",
    "cucharada colmada": "cucharada_colmada",
    "cucharadita": "cucharadita",
}
_CANONICAL_TO_STORAGE = {value: key for key, value in _STORAGE_TO_CANONICAL.items()}
_CANONICAL_TO_STORAGE.update({"vaso": "vaso", "taza": "taza", "plato": "plato", "unidad": "unidad"})


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


def canonical_measure(measure: str) -> str:
    """Return the stable measure id for a user expression or a legacy storage name."""
    key = _key(measure)
    for definition in load_measure_definitions().values():
        names = (definition.measure_id, definition.display_name, *definition.aliases)
        if key in {_key(name) for name in names}:
            return definition.measure_id
    storage_key = SYNONYMS.get(key, key)
    return _STORAGE_TO_CANONICAL.get(storage_key, storage_key)


def measure_label(measure: str) -> str:
    """Human-readable label for a canonical id or legacy measure name."""
    measure_id = canonical_measure(measure)
    definition = load_measure_definitions().get(measure_id)
    return definition.display_name if definition else measure


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


def measure_options(food_id: str, measures: Measures | None = None) -> list[dict[str, object]]:
    """Canonical measure options for a food, including volume and review status."""
    available = measures_of(food_id, measures)
    definitions = load_measure_definitions()
    options = []
    for storage_name, grams in available.items():
        measure_id = canonical_measure(storage_name)
        definition = definitions.get(measure_id)
        options.append(
            {
                "id": measure_id,
                "nombre": definition.display_name if definition else storage_name,
                "gramos": grams,
                "volumen_ml": definition.volume_ml if definition else None,
                "tipo": definition.kind if definition else "food_specific",
                "estado": definition.status if definition else "approved",
            }
        )
    return sorted(options, key=lambda option: str(option["nombre"]))


def to_grams(food_id: str, measure: str, count: float = 1, measures: Measures | None = None) -> float:
    """Grams of `count` × `measure` of a food. Raises ValueError for a count out of range and
    UnknownMeasureError if the food has no standard weight for that measure."""
    if not 0 < count <= MAX_COUNT:
        raise ValueError(f"la cantidad debe estar entre 0 y {MAX_COUNT} (recibido {count:g})")
    available = measures_of(food_id, measures)
    by_key = {_key(name): grams for name, grams in available.items()}
    measure_id = canonical_measure(measure)
    key = _CANONICAL_TO_STORAGE.get(measure_id, measure_id)
    if key not in by_key:
        raise UnknownMeasureError(food_id, measure, sorted(available))
    return round(by_key[key] * count, 1)
