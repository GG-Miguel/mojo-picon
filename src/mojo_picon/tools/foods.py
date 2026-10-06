"""The curated food table (data/foods.csv): loading and validation.

The table is built by data/build_foods.py from official sources (specs/food-table.md).
Validation runs when the table is built and in the test suite (CI).
"""

from __future__ import annotations

import csv
import unicodedata
from collections.abc import Mapping
from pathlib import Path

from mojo_picon.domain import Allergen, Food, Nutrients

DEFAULT_FOODS = Path(__file__).resolve().parents[3] / "data" / "foods.csv"

NUTRIENT_COLUMNS = [
    "kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "sugars_g",
    "saturated_g",
    "fiber_g",
    "sodium_mg",
    "salt_g",
]
FOOD_COLUMNS = [
    "id",
    "name",
    "category",
    *NUTRIENT_COLUMNS,
    "energy_kj",  # as given by the source, when it gives it
    "kcal_derived",  # the source gives no energy: kcal computed from macronutrients (EU factors)
    "source",
    "source_code",
    "source_name",
    "allergens",
    "max_portion_g",
    "section",
    "synonyms",
    "review_note",
]
REQUIRED_NUTRIENTS = ("kcal", "protein_g", "carbs_g", "fat_g")
ENERGY_TOLERANCE = 0.15  # 4·P + 4·C + 9·F (+ 2·fibre) within ±15 % of the stated kcal
ENERGY_CHECK_MIN_KCAL = 20  # below this, relative differences are meaningless (water, tea)


def normalize(text: str) -> str:
    """Lowercase, without accents, single spaces: how names and synonyms are compared."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def parse_row(raw: Mapping[str, str]) -> dict[str, object]:
    """A CSV row with typed values: floats for nutrients, a bool for kcal_derived."""
    row: dict[str, object] = dict(raw)
    for name in [*NUTRIENT_COLUMNS, "energy_kj", "max_portion_g"]:
        value = raw.get(name, "")
        row[name] = float(value) if value not in ("", None) else None
    row["kcal_derived"] = raw.get("kcal_derived") == "true"
    return row


def validate_rows(rows: list[dict[str, object]]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block the build; warnings are flagged for review."""
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    terms: dict[str, str] = {}  # normalised name or synonym -> food id

    for row in rows:
        fid = str(row["id"])
        if fid in seen_ids:
            errors.append(f"{fid}: duplicate id")
        seen_ids.add(fid)
        if not row.get("name"):
            errors.append(f"{fid}: missing name")
        if not row.get("source"):
            errors.append(f"{fid}: missing source")

        missing = [n for n in REQUIRED_NUTRIENTS if row.get(n) is None]
        if missing:
            errors.append(f"{fid}: missing {', '.join(missing)}")
            continue
        for n in NUTRIENT_COLUMNS:
            value = row.get(n)
            if value is not None and float(value) < 0:
                errors.append(f"{fid}: negative {n}")
        protein, carbs, fat, kcal = (float(row[n]) for n in ("protein_g", "carbs_g", "fat_g", "kcal"))
        if protein + carbs + fat > 100.5:
            errors.append(f"{fid}: protein + carbs + fat = {protein + carbs + fat:.1f} g per 100 g")
        if kcal > 905:  # pure fat is ~900 kcal per 100 g
            errors.append(f"{fid}: {kcal:g} kcal per 100 g is not plausible")

        if not row.get("kcal_derived") and kcal >= ENERGY_CHECK_MIN_KCAL:
            estimate = 4 * protein + 4 * carbs + 9 * fat + 2 * float(row.get("fiber_g") or 0)
            if abs(estimate - kcal) > ENERGY_TOLERANCE * kcal:
                warnings.append(f"{fid}: stated {kcal:g} kcal, macronutrients give {estimate:.0f} kcal")
        sodium, salt = row.get("sodium_mg"), row.get("salt_g")
        if (
            sodium is not None
            and salt is not None
            and abs(float(salt) - float(sodium) * 2.5 / 1000) > 0.2 * float(salt) + 0.05
        ):
            warnings.append(f"{fid}: salt {float(salt):g} g does not match sodium {float(sodium):g} mg (x 2.5)")
        for part, whole in (("sugars_g", "carbs_g"), ("saturated_g", "fat_g")):
            if row.get(part) is not None and float(row[part]) > float(row[whole]) + 0.5:
                warnings.append(f"{fid}: {part} greater than {whole}")

        for allergen in filter(None, str(row.get("allergens") or "").split(";")):
            if allergen not in Allergen.__members__.values():
                errors.append(f"{fid}: unknown allergen {allergen!r}")
        max_portion = row.get("max_portion_g")
        if max_portion is None or float(max_portion) <= 0:
            errors.append(f"{fid}: max_portion_g must be positive")

        for term in [str(row.get("name") or ""), *str(row.get("synonyms") or "").split(";")]:
            key = normalize(term)
            if not key:
                continue
            if key in terms and terms[key] != fid:
                errors.append(f"{fid}: «{term}» is also a name or synonym of {terms[key]}")
            terms.setdefault(key, fid)

    return errors, warnings


def row_to_food(row: Mapping[str, object]) -> Food:
    return Food(
        id=str(row["id"]),
        name=str(row["name"]),
        per_100g=Nutrients(
            kcal=row["kcal"],
            protein_g=row["protein_g"],
            carbs_g=row["carbs_g"],
            fat_g=row["fat_g"],
            sugars_g=row.get("sugars_g") or 0,
            saturated_g=row.get("saturated_g") or 0,
            fiber_g=row.get("fiber_g") or 0,
            sodium_mg=row.get("sodium_mg") or 0,
        ),
        allergens=frozenset(Allergen(a) for a in str(row.get("allergens") or "").split(";") if a),
        max_portion_g=row["max_portion_g"],
        category=str(row.get("category") or ""),
        section=str(row.get("section") or ""),
        synonyms=tuple(s for s in str(row.get("synonyms") or "").split(";") if s),
        source=str(row.get("source") or ""),
    )


def load_foods(path: Path = DEFAULT_FOODS) -> dict[str, Food]:
    """Load and validate the food table. Raises ValueError if it is not valid."""
    with path.open(encoding="utf-8") as f:
        rows = [parse_row(r) for r in csv.DictReader(f)]
    errors, _ = validate_rows(rows)
    if errors:
        raise ValueError(f"invalid food table {path}: " + "; ".join(errors[:5]))
    return {str(r["id"]): row_to_food(r) for r in rows}
