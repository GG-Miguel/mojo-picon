import pytest

from mojo_picon.domain import Allergen, Food, MacroTargets, Meal, Nutrients, Plan, PlanItem
from mojo_picon.tools.verify_plan import IssueCode, verify_plan

# Test fixture, not the real food table (data/foods.csv is built from BEDCA/CIQUAL/USDA).
FOODS = {
    f.id: f
    for f in [
        Food(id="rice_cooked", name="Arroz cocido", per_100g=Nutrients(kcal=130, protein_g=2.7, carbs_g=28, fat_g=0.3)),
        Food(
            id="chicken_breast",
            name="Pechuga de pollo",
            per_100g=Nutrients(kcal=165, protein_g=31, carbs_g=0, fat_g=3.6),
        ),
        Food(
            id="olive_oil",
            name="Aceite de oliva",
            per_100g=Nutrients(kcal=884, protein_g=0, carbs_g=0, fat_g=100),
            max_portion_g=30,
        ),
        Food(
            id="almonds",
            name="Almendras",
            per_100g=Nutrients(kcal=579, protein_g=21, carbs_g=22, fat_g=50),
            allergens=frozenset({Allergen.TREE_NUTS}),
            max_portion_g=50,
        ),
    ]
}

# 150 g rice + 150 g chicken + 10 g oil = 530.9 kcal, 50.55 g protein, 42 g carbs, 15.85 g fat
DINNER = Plan(
    meals=[
        Meal(
            name="cena",
            items=[
                PlanItem(food_id="rice_cooked", grams=150),
                PlanItem(food_id="chicken_breast", grams=150),
                PlanItem(food_id="olive_oil", grams=10),
            ],
        )
    ]
)
EXACT = MacroTargets(kcal=531, protein_g=51, carbs_g=42, fat_g=16)


def codes(result):
    return [i.code for i in result.issues]


def test_plan_matching_the_remaining_target_passes():
    result = verify_plan(DINNER, EXACT, frozenset(), FOODS)
    assert result.passed
    assert result.totals.kcal == pytest.approx(530.9)


def test_kcal_within_10_percent_passes_and_outside_fails():
    assert verify_plan(DINNER, EXACT.model_copy(update={"kcal": 580}), frozenset(), FOODS).passed  # -8.5 %
    result = verify_plan(DINNER, EXACT.model_copy(update={"kcal": 620}), frozenset(), FOODS)  # -14 %
    assert codes(result) == [IssueCode.KCAL_OUT_OF_RANGE]
    assert result.issues[0].message.startswith("kcal −14 %")


def test_low_protein_gives_an_actionable_message():
    # The demo case: "proteína −18 %" -> the Planner corrects.
    result = verify_plan(DINNER, EXACT.model_copy(update={"protein_g": 62}), frozenset(), FOODS)
    assert codes(result) == [IssueCode.MACRO_OUT_OF_RANGE]
    assert result.issues[0].message == "proteína −18 % (51 g frente a 62 g)"


def test_small_macro_remainders_use_the_absolute_floor():
    # 10 g of fat remaining: 15.85 g planned is +58 % but within the 8 g floor.
    assert verify_plan(DINNER, EXACT.model_copy(update={"fat_g": 10}), frozenset(), FOODS).passed


def test_user_allergen_fails():
    plan = Plan(meals=[Meal(name="merienda", items=[PlanItem(food_id="almonds", grams=30)])])
    remaining = MacroTargets(kcal=174, protein_g=6, carbs_g=7, fat_g=15)
    result = verify_plan(plan, remaining, frozenset({Allergen.TREE_NUTS}), FOODS)
    assert codes(result) == [IssueCode.ALLERGEN]
    assert "Almendras" in result.issues[0].message


def test_unrealistic_quantity_fails():
    plan = Plan(meals=[Meal(name="cena", items=[PlanItem(food_id="olive_oil", grams=60)])])
    result = verify_plan(plan, MacroTargets(kcal=530, protein_g=0, carbs_g=0, fat_g=60), frozenset(), FOODS)
    assert IssueCode.UNREALISTIC_QUANTITY in codes(result)


def test_unknown_food_fails_without_inventing_nutrients():
    plan = Plan(meals=[Meal(name="cena", items=[PlanItem(food_id="dragon_fruit_burger", grams=200)])])
    result = verify_plan(plan, EXACT, frozenset(), FOODS)
    assert IssueCode.UNKNOWN_FOOD in codes(result)
    assert result.totals.kcal == 0


def test_nothing_remaining_fails():
    result = verify_plan(DINNER, MacroTargets(kcal=-50, protein_g=0, carbs_g=0, fat_g=0), frozenset(), FOODS)
    assert codes(result) == [IssueCode.NOTHING_REMAINING]
