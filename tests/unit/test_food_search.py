import pytest

from mojo_picon.domain import Allergen
from mojo_picon.tools.food_search import (
    FoodIndex,
    SearchStatus,
    UnknownFoodError,
    _edit_distance,
    check_allergens,
    get_nutrients,
)
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
INDEX = FoodIndex(FOODS)


def ids(result):
    return [c.food_id for c in result.candidates]


# --- exact matches: names, synonyms, accents, plurals ------------------------------


@pytest.mark.parametrize(
    ("query", "food_id"),
    [
        ("tomate", "tomate"),
        ("Tomates", "tomate"),  # plural and case
        ("platano", "platano"),  # without accent
        ("nuez", "nueces"),  # singular of a plural name
        ("AOVE", "aceite_oliva"),  # synonym
        ("millo", "maiz_dulce"),  # Canary synonym
        ("café con leche", "cafe_con_leche"),  # inner stopword kept
        ("queso majorero", "queso_majorero"),
        ("gofio", "gofio"),
    ],
)
def test_exact_match(query, food_id):
    result = INDEX.search(query)
    assert result.status is SearchStatus.EXACT
    assert ids(result) == [food_id]
    assert result.candidates[0].confidence == 1.0


# --- ambiguity: the agent must ask ---------------------------------------------------


def test_generic_word_is_ambiguous_with_the_synonym_first():
    # «¿arroz blanco o integral?» (specs/food-table.md)
    result = INDEX.search("arroz")
    assert result.status is SearchStatus.AMBIGUOUS
    assert ids(result)[0] == "arroz_blanco_cocido"
    assert {"arroz_integral_cocido", "arroz_blanco_crudo"} <= set(ids(result))


def test_ambiguity_is_limited_to_the_same_category():
    # «pollo» -> breast or thigh, never a dish that only mentions chicken
    result = INDEX.search("pollo")
    assert result.status is SearchStatus.AMBIGUOUS
    assert {FOODS[i].category for i in ids(result)} == {"carnes"}


def test_partial_names_return_several_candidates():
    result = INDEX.search("queso")
    assert result.status is SearchStatus.AMBIGUOUS
    assert all(c.confidence < 1.0 for c in result.candidates)
    assert len(result.candidates) <= 5


# --- typos and filler words ------------------------------------------------------------


def test_typos_are_corrected_but_never_exact():
    result = INDEX.search("platno")
    assert result.status is SearchStatus.APPROXIMATE
    assert ids(result) == ["platano"]
    assert result.candidates[0].confidence < 1.0


def test_filler_words_are_ignored():
    result = INDEX.search("un plato de arroz")
    assert ids(result)[0] == "arroz_blanco_cocido"
    assert result.candidates[0].confidence < 1.0


def test_short_words_are_not_treated_as_typos():
    # «plato» is not a typo of «plátano», nor «pieza» of «pizza»
    assert INDEX.search("una pieza de fruta").status is SearchStatus.NOT_FOUND


@pytest.mark.parametrize("query", ["arroz con pollo", "arros con pollo"])
def test_mixed_dishes_not_in_the_table_are_not_reduced_to_one_ingredient(query):
    # The agent has to search each food separately
    assert INDEX.search(query).status is SearchStatus.NOT_FOUND


@pytest.mark.parametrize("query", ["fruta del dragón", "", "   ", "!!!"])
def test_not_found_never_invents(query):
    result = INDEX.search(query)
    assert result.status is SearchStatus.NOT_FOUND
    assert result.candidates == []


@pytest.mark.parametrize(("a", "b", "distance"), [("arros", "arroz", 1), ("platno", "platano", 1), ("ab", "ba", 1)])
def test_edit_distance(a, b, distance):
    assert _edit_distance(a, b) == distance


# --- get_nutrients and check_allergens -------------------------------------------------


def test_get_nutrients_scales_per_100_g():
    per_100 = get_nutrients(FOODS, "aceite_oliva")
    ten_grams = get_nutrients(FOODS, "aceite_oliva", 10)
    assert ten_grams.kcal == pytest.approx(per_100.kcal / 10)


@pytest.mark.parametrize("grams", [0, -5])
def test_get_nutrients_rejects_non_positive_grams(grams):
    with pytest.raises(ValueError):
        get_nutrients(FOODS, "aceite_oliva", grams)


def test_get_nutrients_unknown_food():
    with pytest.raises(UnknownFoodError):
        get_nutrients(FOODS, "dragon_fruit")


def test_check_allergens_returns_only_matches():
    result = check_allergens(FOODS, ["almendras", "tomate", "pan_blanco"], frozenset({Allergen.TREE_NUTS}))
    assert result == {"almendras": frozenset({Allergen.TREE_NUTS})}


def test_check_allergens_unknown_food():
    with pytest.raises(UnknownFoodError):
        check_allergens(FOODS, ["dragon_fruit"], frozenset({Allergen.GLUTEN}))
