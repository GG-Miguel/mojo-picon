"""Build data/foods.csv from the curated target list and official food composition tables.

Sources (specs/food-table.md):
- CIQUAL 2020 (ANSES, Etalab 2.0): main source. Download the English Excel table to
  data/raw/ciqual_2020_en.xls (see data/DATASHEET.md).
- BEDCA (AESAN): only for Spanish and Canary products missing in CIQUAL (rows with a `bedca_id`).
  Used as educational use while AESAN answers the authorisation request and the repository is
  private (ADR-25). Download first with data/fetch_bedca.py. With --no-bedca, those rows fall back
  to their recipe or approximation: use it for any public release until AESAN authorises.
- Recipes and approximations are computed from other rows of the table.

Run: uv run --group data python data/build_foods.py [--no-bedca]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA_DIR.parent / "src"))

from mojo_picon.tools.foods import FOOD_COLUMNS, NUTRIENT_COLUMNS, validate_rows  # noqa: E402

CIQUAL_COLUMNS = {
    "kcal": "Energy, Regulation EU No 1169/2011 (kcal/100g)",
    "protein_g": "Protein (g/100g)",
    "carbs_g": "Carbohydrate (g/100g)",
    "fat_g": "Fat (g/100g)",
    "sugars_g": "Sugars (g/100g)",
    "saturated_g": "FA saturated (g/100g)",
    "fiber_g": "Fibres (g/100g)",
    "sodium_mg": "Sodium (mg/100g)",
    "salt_g": "Salt (g/100g)",
    "polyols_g": "Polyols (g/100g)",
    "alcohol_g": "Alcohol (g/100g)",
    "organic_acids_g": "Organic acids (g/100g)",
}

CIQUAL_KJ_COLUMN = "Energy, Regulation EU No 1169/2011 (kJ/100g)"

# BEDCA component codes (EuroFIR) -> our columns. Values are copied verbatim.
BEDCA_COMPONENTS = {
    "PROT": "protein_g",
    "CHO": "carbs_g",
    "FAT": "fat_g",
    "FIBT": "fiber_g",
    "SUGAR": "sugars_g",
    "FASAT": "saturated_g",
    "NA": "sodium_mg",
}
KJ_PER_KCAL = 4.184
BEDCA_SOURCE = "BEDCA (educational use; AESAN authorisation requested 2026-10-12)"

# Energy conversion factors of Regulation (EU) 1169/2011, Annex XIV (kcal per g).
ENERGY_FACTORS = {
    "protein_g": 4,
    "carbs_g": 4,
    "fat_g": 9,
    "fiber_g": 2,
    "polyols_g": 2.4,
    "alcohol_g": 7,
    "organic_acids_g": 3,
}


@dataclass
class Report:
    built: list[str] = field(default_factory=list)
    derived_kcal: list[str] = field(default_factory=list)
    approximations: list[str] = field(default_factory=list)
    bedca: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_ciqual_value(raw: object) -> float | None:
    """CIQUAL cells are text: "12,3", "traces", "< 0,5" or "-" (no data).

    Rules (documented in DATASHEET.md): "-" or empty -> missing; "traces" -> 0;
    "< x" -> x / 2 (middle-bound convention).
    """
    if isinstance(raw, float | int):
        return float(raw)
    text = str(raw).strip().replace(",", ".")
    if text in ("", "-"):
        return None
    if text.lower() == "traces":
        return 0.0
    if text.startswith("<"):
        return float(text[1:].strip()) / 2
    return float(text)


def load_ciqual(path: Path) -> dict[str, dict[str, object]]:
    import xlrd  # only needed to build the table

    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    header = sheet.row_values(0)
    index = {name: header.index(col) for name, col in CIQUAL_COLUMNS.items()}
    kj = header.index(CIQUAL_KJ_COLUMN)
    foods = {}
    for r in range(1, sheet.nrows):
        row = sheet.row_values(r)
        code = str(int(row[header.index("alim_code")]))
        foods[code] = {"source_name": row[header.index("alim_nom_eng")], "energy_kj": parse_ciqual_value(row[kj])} | {
            name: parse_ciqual_value(row[i]) for name, i in index.items()
        }
    return foods


def load_bedca(cache_dir: Path, food_id: str) -> dict[str, object] | None:
    """Values of one BEDCA food from the cache written by fetch_bedca.py, verbatim.

    Only values per 100 g of edible portion (moex "W") are used; others (e.g. "WKG", per kg) are left
    out rather than converted, because BEDCA values may not be modified. Value type "TR" (traces)
    with no number -> 0, as with CIQUAL. BEDCA gives energy only in kJ: kept as `energy_kj`.
    """
    path = cache_dir / f"{food_id}.xml"
    if not path.exists():
        return None
    xml = path.read_text(encoding="utf-8")
    name = re.search(r"<f_ori_name>([^<]*)</f_ori_name>", xml)
    values: dict[str, object] = {"source_name": name.group(1) if name else "", "skipped": []}
    pattern = (
        r"<eur_name>([^<]*)</eur_name><best_location>([^<]*)</best_location><v_unit>([^<]*)</v_unit>"
        r"<moex>([^<]*)</moex><value_type>([^<]*)</value_type>"
    )
    for eur_name, value, unit, moex, value_type in re.findall(pattern, xml):
        if eur_name != "ENERC" and eur_name not in BEDCA_COMPONENTS:
            continue
        if moex != "W":
            values["skipped"].append(f"{eur_name} given as {moex}, not per 100 g")
            continue
        number = float(value) if value else (0.0 if value_type == "TR" else None)
        if eur_name == "ENERC":
            if unit == "kJ":
                values["energy_kj"] = number
        else:
            values[BEDCA_COMPONENTS[eur_name]] = number
    return values


def derive_kcal(values: dict[str, object]) -> float:
    return sum(factor * (values.get(name) or 0) for name, factor in ENERGY_FACTORS.items())


def build(
    targets_path: Path, ciqual_path: Path, bedca_dir: Path | None = None
) -> tuple[list[dict[str, object]], Report]:
    report = Report()
    ciqual = load_ciqual(ciqual_path)
    with targets_path.open(encoding="utf-8") as f:
        targets = list(csv.DictReader(f))

    rows: dict[str, dict[str, object]] = {}
    deferred = []  # recipes and approximations need the rows they are built from

    for t in targets:
        base = {k: t[k] for k in ("id", "name", "category", "allergens", "max_portion_g", "section", "synonyms")}
        base["review_note"] = t["review_note"]
        source = t["source"]
        if source == "ciqual":
            values = ciqual.get(t["source_code"])
            if values is None:
                report.errors.append(f"{t['id']}: CIQUAL code {t['source_code']} not found")
                continue
            if any(values[m] is None for m in ("protein_g", "carbs_g", "fat_g")):
                report.errors.append(f"{t['id']}: CIQUAL {t['source_code']} lacks protein, carbs or fat")
                continue
            kcal_derived = values["kcal"] is None
            if kcal_derived:
                values = values | {"kcal": round(derive_kcal(values), 1)}
                report.derived_kcal.append(t["id"])
            rows[t["id"]] = (
                base
                | {n: values[n] for n in NUTRIENT_COLUMNS}
                | {
                    "energy_kj": values["energy_kj"],
                    "kcal_derived": kcal_derived,
                    "source": "CIQUAL 2020",
                    "source_code": t["source_code"],
                    "source_name": values["source_name"],
                }
            )
        elif source == "bedca":
            report.pending.append(f"{t['id']} ({t['name']}): BEDCA, pending AESAN authorisation")
        elif source in ("recipe", "approx"):
            deferred.append((t, base))
        else:
            report.errors.append(f"{t['id']}: unknown source {source!r}")

    for t, base in deferred:
        if t["source"] == "approx":
            ref = rows.get(t["source_code"])
            if ref is None:
                report.errors.append(f"{t['id']}: approximation of missing row {t['source_code']}")
                continue
            rows[t["id"]] = (
                ref | base | {"source": f"approximation of {t['source_code']}", "source_code": "", "source_name": ""}
            )
            report.approximations.append(f"{t['id']} ≈ {t['source_code']}")
        else:
            parts = [p.split(":") for p in t["source_code"].split(";")]
            missing = [food_id for food_id, _ in parts if food_id not in rows]
            if missing:
                report.errors.append(f"{t['id']}: recipe uses missing rows {missing}")
                continue
            total = sum(float(g) for _, g in parts)
            if abs(total - 100) > 0.01:
                report.errors.append(f"{t['id']}: recipe grams add up to {total}, not 100")
                continue
            # A nutrient missing in any ingredient stays missing in the recipe (not counted as 0)
            nutrients = {
                n: None
                if any(rows[food_id][n] is None for food_id, _ in parts)
                else sum(float(g) / 100 * rows[food_id][n] for food_id, g in parts)
                for n in NUTRIENT_COLUMNS
            }
            rows[t["id"]] = (
                base
                | {n: None if v is None else round(v, 2) for n, v in nutrients.items()}
                | {
                    "kcal_derived": any(rows[food_id]["kcal_derived"] for food_id, _ in parts),
                    "source": "recipe",
                    "source_code": t["source_code"],
                    "source_name": "",
                }
            )
            report.approximations.append(f"{t['id']} = recipe {t['source_code']}")

    if bedca_dir is not None:
        _apply_bedca(targets, rows, bedca_dir, report)

    ordered = [rows[t["id"]] for t in targets if t["id"] in rows]
    report.built = [r["id"] for r in ordered]
    errors, warnings = validate_rows(ordered)
    report.errors += errors
    report.warnings += warnings
    return ordered, report


def _apply_bedca(targets: list[dict[str, str]], rows: dict[str, dict[str, object]], bedca_dir: Path, report: Report):
    """Replace the fallback (CIQUAL food, recipe or approximation) with BEDCA values when available."""
    for t in targets:
        food_id = t.get("bedca_id")
        if not food_id:
            continue
        fallback = rows.get(t["id"])
        values = load_bedca(bedca_dir, food_id)
        if values is None:
            report.warnings.append(f"{t['id']}: BEDCA {food_id} not downloaded (run fetch_bedca.py); fallback used")
            continue
        if values.get("energy_kj") is None or any(values.get(m) is None for m in ("protein_g", "carbs_g", "fat_g")):
            report.warnings.append(f"{t['id']}: BEDCA {food_id} lacks energy or macronutrients; fallback used")
            continue
        kcal = round(float(values["energy_kj"]) / KJ_PER_KCAL, 1)
        rows[t["id"]] = (
            {k: t[k] for k in ("id", "name", "category", "allergens", "max_portion_g", "section", "synonyms")}
            | {n: values.get(n) for n in NUTRIENT_COLUMNS}
            | {
                "kcal": kcal,
                "salt_g": None,  # not given by BEDCA; we do not derive values into BEDCA rows
                "energy_kj": values["energy_kj"],
                "kcal_derived": False,  # converted from the stated kJ, not computed from macronutrients
                "source": BEDCA_SOURCE,
                "source_code": food_id,
                "source_name": values["source_name"],
                "review_note": "; ".join(
                    [
                        "kcal = energy_kj / 4.184",
                        "Fallback without BEDCA: " + (fallback["source"] if fallback else "none"),
                    ]
                    + values["skipped"]
                ),
            }
        )
        before = f"{fallback['kcal']:g} kcal ({fallback['source']})" if fallback else "no fallback"
        report.bedca.append(f"{t['id']}: {kcal:g} kcal from BEDCA «{values['source_name']}»; fallback {before}")


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FOOD_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in FOOD_COLUMNS})


def write_report(report: Report, path: Path) -> None:
    def section(title: str, items: list[str]) -> str:
        body = "\n".join(f"- {i}" for i in items) if items else "- (none)"
        return f"## {title} ({len(items)})\n{body}\n"

    path.write_text(
        "# Food table build report\n\n"
        "Generated by `data/build_foods.py`. Do not edit by hand.\n\n"
        + section("Errors", report.errors)
        + "\n"
        + section("Warnings (to review)", report.warnings)
        + "\n"
        + section("Energy derived from macronutrients (EU 1169/2011 factors)", report.derived_kcal)
        + "\n"
        + section("Recipes and approximations", report.approximations)
        + "\n"
        + section("BEDCA rows (educational use, authorisation pending) vs fallback", report.bedca)
        + "\n"
        + section("Pending (not in foods.csv)", report.pending)
        + f"\nRows built: {len(report.built)}\n",
        encoding="utf-8",
    )


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--targets", type=Path, default=DATA_DIR / "food_targets.csv")
    parser.add_argument("--ciqual", type=Path, default=DATA_DIR / "raw" / "ciqual_2020_en.xls")
    parser.add_argument("--out", type=Path, default=DATA_DIR / "foods.csv")
    parser.add_argument("--report", type=Path, default=DATA_DIR / "foods_report.md")
    parser.add_argument("--bedca-dir", type=Path, default=DATA_DIR / "raw" / "bedca")
    parser.add_argument("--no-bedca", action="store_true", help="use recipes and approximations instead of BEDCA")
    args = parser.parse_args()

    rows, report = build(args.targets, args.ciqual, None if args.no_bedca else args.bedca_dir)
    write_report(report, args.report)
    if report.errors:
        print(f"{len(report.errors)} errors; foods.csv not written. See {args.report}", file=sys.stderr)
        return 1
    write_csv(rows, args.out)
    print(
        f"{len(rows)} foods written to {args.out} "
        f"({len(report.bedca)} from BEDCA, {len(report.derived_kcal)} with derived energy, "
        f"{len(report.warnings)} warnings, {len(report.pending)} pending)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
