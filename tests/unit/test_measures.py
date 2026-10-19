import csv

import pytest

from mojo_picon.tools.diary import MAX_LOGGED_PORTION_FACTOR
from mojo_picon.tools.foods import load_foods
from mojo_picon.tools.measures import (
    DEFAULT_MEASURES,
    MAX_COUNT,
    UnknownMeasureError,
    canonical_measure,
    measure_options,
    measures_of,
    to_grams,
)


def test_household_measures_become_grams_of_edible_portion():
    assert to_grams("aceite_oliva", "cucharada") == 10  # Carbajal: cucharada sopera rasa
    assert to_grams("manzana", "unidad", 2) == 336  # 200 g as bought x 0.84 edible (BEDCA) x 2
    assert to_grams("huevo", "unidad") == 53  # 60 g with shell x 0.88


@pytest.mark.parametrize(
    ("measure", "grams"),
    [("cucharadas", 10), ("Cucharada sopera", 10), ("cucharilla", 5), ("cucharada colmada", 14)],
)
def test_what_users_say_matches_the_table(measure, grams):
    assert to_grams("aceite_oliva", measure) == grams


@pytest.mark.parametrize(
    ("spoken", "canonical"),
    [
        ("vasito", "vaso"),
        ("una taza", "taza"),
        ("taza", "taza"),
        ("cuchara sopera", "cucharada_sopera"),
        ("cuchara de café", "cucharadita"),
        ("cucharada de postre", "cucharadita"),
        ("plato estándar", "plato"),
    ],
)
def test_conversational_measure_aliases_have_canonical_ids(spoken, canonical):
    assert canonical_measure(spoken) == canonical


def test_canonical_measure_ids_are_accepted_by_conversion():
    assert to_grams("aceite_oliva", "cucharada_sopera") == 10
    assert to_grams("aceite_oliva", "cucharadita") == 5


def test_measure_options_expose_canonical_name_and_volume():
    options = measure_options("leche_semidesnatada")
    vaso = next(option for option in options if option["id"] == "vaso")
    assert vaso["nombre"] == "vaso"
    assert vaso["volumen_ml"] == 200
    assert vaso["estado"] == "approved"


def test_standard_plate_is_marked_provisional_until_reviewed():
    assert to_grams("arroz_blanco_cocido", "plato estándar") == 250
    assert any(
        option["id"] == "plato" and option["estado"] == "provisional"
        for option in measure_options("arroz_blanco_cocido")
    )


def test_plurals_and_pieces():
    assert to_grams("cerveza", "cañas", 2) == 400
    assert to_grams("platano", "pieza") == 106
    assert to_grams("pan_molde", "rebanadas", 2) == 40


def test_an_unknown_measure_lists_the_available_ones():
    with pytest.raises(UnknownMeasureError) as e:
        to_grams("apio", "plato")
    assert e.value.available == []
    with pytest.raises(UnknownMeasureError) as e:
        to_grams("manzana", "cucharada")
    assert "unidad" in e.value.available


@pytest.mark.parametrize("count", [0, -1, MAX_COUNT + 1])
def test_counts_out_of_range_are_rejected(count):
    with pytest.raises(ValueError):
        to_grams("manzana", "unidad", count)


def test_every_row_is_a_known_food_with_consistent_grams():
    foods = load_foods()
    with DEFAULT_MEASURES.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    for row in rows:
        assert row["food_id"] in foods, row
        portion = float(row["edible_portion"])
        assert 0 < portion <= 1, row
        assert float(row["grams"]) == round(float(row["purchase_grams"]) * portion), row
        # one measure fits in what the diary accepts for one food (the planner's max portion x 3)
        assert float(row["grams"]) <= foods[row["food_id"]].max_portion_g * MAX_LOGGED_PORTION_FACTOR, row
        assert row["source"].startswith(("Carbajal", "Mojo Picón provisional")), row
    assert measures_of("leche_semidesnatada")["vaso"] == 200


def test_log_meal_takes_grams_or_a_measure_but_not_both():
    from pydantic import ValidationError

    from mojo_picon.agents.tools import MealPortion

    assert MealPortion(food_id="manzana", measure="unidad", count=2).grams is None
    assert MealPortion(food_id="arroz_blanco_cocido", grams=250).measure is None
    for wrong in ({"food_id": "manzana"}, {"food_id": "manzana", "grams": 150, "measure": "unidad"}):
        with pytest.raises(ValidationError):
            MealPortion(**wrong)
