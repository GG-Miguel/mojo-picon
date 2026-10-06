import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from mojo_picon.domain import Allergen
from mojo_picon.tools.foods import DEFAULT_FOODS, load_foods, normalize, parse_row, validate_rows

BUILD_SCRIPT = Path(__file__).resolve().parents[2] / "data" / "build_foods.py"


def _rows():
    with DEFAULT_FOODS.open(encoding="utf-8") as f:
        return [parse_row(r) for r in csv.DictReader(f)]


# --- the committed table (also checked in CI) ------------------------------------


def test_committed_table_is_valid():
    errors, _ = validate_rows(_rows())
    assert errors == []


def test_committed_table_loads_as_domain_foods():
    foods = load_foods()
    assert len(foods) >= 190
    assert foods["almendras"].allergens == frozenset({Allergen.TREE_NUTS})
    assert foods["pechuga_pollo_plancha"].per_100g.protein_g > 25


@pytest.mark.parametrize("food_id", ["arroz_blanco_cocido", "pechuga_pollo_plancha", "aceite_oliva", "lechuga"])
def test_demo_foods_are_present(food_id):
    assert food_id in load_foods()


def test_every_row_has_a_traceable_source():
    for row in _rows():
        if row["source"] == "CIQUAL 2020":
            assert row["source_code"] and row["source_name"], row["id"]


# --- validation rules -------------------------------------------------------------

VALID = {
    "id": "x",
    "name": "Alimento",
    "kcal": 100.0,
    "protein_g": 5.0,
    "carbs_g": 15.0,
    "fat_g": 2.0,
    "fiber_g": 0.0,
    "kcal_derived": False,
    "source": "CIQUAL 2020",
    "allergens": "",
    "max_portion_g": 200.0,
    "synonyms": "",
}


def test_valid_row_passes():
    assert validate_rows([VALID]) == ([], [])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"kcal": None}, "missing kcal"),
        ({"protein_g": -1.0}, "negative protein_g"),
        ({"protein_g": 50.0, "carbs_g": 40.0, "fat_g": 20.0}, "protein + carbs + fat"),
        ({"allergens": "nuts"}, "unknown allergen"),
        ({"max_portion_g": 0.0}, "max_portion_g"),
        ({"source": ""}, "missing source"),
    ],
)
def test_invalid_rows_are_errors(change, message):
    errors, _ = validate_rows([VALID | change])
    assert any(message in e for e in errors), errors


def test_duplicate_synonyms_across_foods_are_errors():
    a = VALID | {"id": "a", "name": "Papa", "synonyms": "patata"}
    b = VALID | {"id": "b", "name": "Patata"}  # accents and case are ignored
    errors, _ = validate_rows([a, b])
    assert any("also a name or synonym of a" in e for e in errors)


def test_inconsistent_energy_is_a_warning_not_an_error():
    errors, warnings = validate_rows([VALID | {"kcal": 300.0}])
    assert errors == []
    assert any("macronutrients give" in w for w in warnings)


def test_normalize_ignores_accents_case_and_spaces():
    assert normalize("  Plátano  de CANARIAS ") == "platano de canarias"


# --- CIQUAL value parsing (build script) -------------------------------------------


@pytest.fixture(scope="module")
def build_module():
    spec = importlib.util.spec_from_file_location("build_foods", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("raw", "value"), [("12,3", 12.3), ("-", None), ("", None), ("traces", 0.0), ("< 0,5", 0.25), (7.0, 7.0)]
)
def test_parse_ciqual_value(build_module, raw, value):
    assert build_module.parse_ciqual_value(raw) == value


def test_derived_energy_uses_eu_factors(build_module):
    values = {"protein_g": 10, "carbs_g": 20, "fat_g": 5, "fiber_g": 3, "alcohol_g": 1}
    assert build_module.derive_kcal(values) == 4 * 10 + 4 * 20 + 9 * 5 + 2 * 3 + 7 * 1


# --- BEDCA (build script) -----------------------------------------------------------

BEDCA_XML = """<?xml version="1.0" encoding="utf-8"?>
<foodresponse><food><f_id>722</f_id><f_ori_name>Queso majorero</f_ori_name>
<foodvalue><eur_name>PROT</eur_name><best_location>25.66</best_location><v_unit>g</v_unit><moex>W</moex><value_type>AV</value_type></foodvalue>
<foodvalue><eur_name>ENERC</eur_name><best_location>1499.97</best_location><v_unit>kJ</v_unit><moex>W</moex><value_type>BE</value_type></foodvalue>
<foodvalue><eur_name>FAT</eur_name><best_location>28.75</best_location><v_unit>g</v_unit><moex>W</moex><value_type>AV</value_type></foodvalue>
<foodvalue><eur_name>CHO</eur_name><best_location></best_location><v_unit>g</v_unit><moex>W</moex><value_type>TR</value_type></foodvalue>
<foodvalue><eur_name>NA</eur_name><best_location>8001.86</best_location><v_unit>mg</v_unit><moex>WKG</moex><value_type>AV</value_type></foodvalue>
<foodvalue><eur_name>FASAT</eur_name><best_location></best_location><v_unit>g</v_unit><moex>W</moex><value_type>BL</value_type></foodvalue>
</food></foodresponse>"""


def test_load_bedca_keeps_values_verbatim(build_module, tmp_path):
    (tmp_path / "722.xml").write_text(BEDCA_XML, encoding="utf-8")
    values = build_module.load_bedca(tmp_path, "722")
    assert values["source_name"] == "Queso majorero"
    assert values["energy_kj"] == 1499.97  # BEDCA gives kJ only; kept as given
    assert values["protein_g"] == 25.66
    assert values["carbs_g"] == 0.0  # "TR" (traces) without a number
    assert values["saturated_g"] is None  # empty value, not traces
    assert "sodium_mg" not in values  # per kg ("WKG"): left out, not converted
    assert values["skipped"] == ["NA given as WKG, not per 100 g"]


def test_load_bedca_missing_file_returns_none(build_module, tmp_path):
    assert build_module.load_bedca(tmp_path, "999") is None


def test_salt_and_sodium_mismatch_is_a_warning():
    _, warnings = validate_rows([VALID | {"sodium_mg": 400.0, "salt_g": 3.0}])
    assert any("does not match sodium" in w for w in warnings)
