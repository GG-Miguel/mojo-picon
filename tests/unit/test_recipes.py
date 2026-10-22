import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from tests.fakes import FakeProvider, tool_call

from mojo_picon.agents import AgentContext, build_graph
from mojo_picon.auth import UserContext
from mojo_picon.domain import Allergen, Nutrients, Profile, Sex
from mojo_picon.guardrails.rules import GuardDecision
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.food_search import FoodIndex
from mojo_picon.tools.foods import load_foods
from mojo_picon.tools.recipes import RecipeError, build_user_recipe, load_recipes, matching

FOODS = load_foods()
USER = UserContext(uid="uid-recetas")
PROFILE = Profile(age=30, sex=Sex.MALE, weight_kg=75, height_cm=178, allergens=frozenset({Allergen.FISH}))
OK = GuardDecision(level="ok", category="none")


def test_every_recipe_of_the_library_fits_the_food_table():
    library = load_recipes(FOODS)
    assert len(library) >= 15
    for recipe, food in library.values():
        assert food.serving_g == pytest.approx(sum(recipe.ingredientes.values()) / recipe.raciones, abs=0.1)
        assert food.max_portion_g == sum(recipe.ingredientes.values())
        assert recipe.validado is False  # until the author or a dietitian reviews them


def test_a_recipe_has_the_sum_of_its_ingredients_and_all_their_allergens():
    recipe, food = load_recipes(FOODS)["receta_macarrones_atun"]
    total = Nutrients.zero()
    for food_id, grams in recipe.ingredientes.items():
        total = total + FOODS[food_id].nutrients_for(grams)
    assert food.nutrients_for(sum(recipe.ingredientes.values())).kcal == pytest.approx(total.kcal)
    assert food.allergens == frozenset().union(*(FOODS[f].allergens for f in recipe.ingredientes))
    assert Allergen.FISH in food.allergens  # the tuna


def test_a_user_recipe_only_takes_foods_of_the_table_and_credible_amounts():
    food = build_user_recipe("Mis lentejas", 3, {"lentejas_cocidas": 600, "chorizo": 60}, FOODS)
    assert food.id == "mireceta_mis_lentejas" and food.serving_g == 220 and food.category == "mis_recetas"
    with pytest.raises(RecipeError, match="no están en la tabla"):
        build_user_recipe("Inventada", 2, {"carne_de_unicornio": 200}, FOODS)
    with pytest.raises(RecipeError, match="mayor que 0"):
        build_user_recipe("Vacía", 2, {"lentejas_cocidas": 0}, FOODS)
    with pytest.raises(RecipeError, match="como mucho"):
        build_user_recipe("Enorme", 2, {"lentejas_cocidas": 9000}, FOODS)
    with pytest.raises(RecipeError, match="raciones"):
        build_user_recipe("Sin raciones", 0, {"lentejas_cocidas": 300}, FOODS)


def test_recipes_are_found_by_name_or_tag():
    index = [(rid, rec.nombre, rec.etiquetas) for rid, (rec, _) in load_recipes(FOODS).items()]
    assert "receta_lentejas_estofadas" in matching(index, "lentejas")
    assert "receta_papas_mojo_cherne" in matching(index, "canaria")


@pytest.fixture
async def context():
    store = InMemoryStore()
    await store.save_profile(USER, PROFILE)
    return AgentContext(user=USER, store=store, foods=FOODS, food_index=FoodIndex(FOODS),
                        activities=load_met_table(), profile=PROFILE)  # fmt: skip


def results(state) -> list[dict]:
    return [json.loads(m.text) for m in state["messages"] if isinstance(m, ToolMessage)]


async def test_one_serving_of_a_recipe_is_logged_in_grams_by_code(context):
    serving = load_recipes(FOODS)["receta_lentejas_estofadas"][1].serving_g
    coach = [tool_call("log_meal", items=[{"food_id": "receta_lentejas_estofadas", "measure": "racion", "count": 2}]),
             AIMessage("Apuntadas dos raciones de lentejas.")]  # fmt: skip
    state = await build_graph(FakeProvider(guardian=[OK], coach=coach), FOODS).ainvoke(
        {"messages": [HumanMessage("Me he comido dos raciones de lentejas")]}, context=context
    )
    [logged] = results(state)
    assert logged["medidas_estandar"] == [f"2 × ración de Lentejas estofadas con chorizo = {2 * serving:g} g"]


async def test_the_recipe_search_flags_the_users_allergens(context):
    coach = [tool_call("search_recipes", query="pescado"), AIMessage("Te propongo una receta sin pescado.")]
    state = await build_graph(FakeProvider(guardian=[OK], coach=coach), FOODS).ainvoke(
        {"messages": [HumanMessage("¿Qué ceno?")]}, context=context
    )
    [found] = results(state)
    assert found["recetas"] and all(r["alergenos_del_usuario"] == ["fish"] for r in found["recetas"])
    assert all(r["por_racion"]["kcal"] > 0 for r in found["recetas"])


async def test_a_confirmed_user_recipe_is_saved_with_the_products_and_found_again(context):
    ingredients = [{"food_id": "lentejas_cocidas", "grams": 600}, {"food_id": "chorizo", "grams": 60}]
    save = AIMessage(
        "",
        tool_calls=[
            {
                "name": "save_recipe",
                "id": "call-save",
                "type": "tool_call",
                "args": {"name": "Mis lentejas", "servings": 3, "ingredients": ingredients},
            }
        ],
    )
    coach = [save,
             tool_call("search_recipes", query="mis lentejas"), AIMessage("Guardada.")]  # fmt: skip
    state = await build_graph(FakeProvider(guardian=[OK], coach=coach), FOODS).ainvoke(
        {"messages": [HumanMessage("Guárdame mis lentejas")]}, context=context
    )
    saved, found = results(state)
    assert saved["guardada"]["food_id"] == "mireceta_mis_lentejas" and saved["guardada"]["racion_g"] == 220
    assert [r["food_id"] for r in found["recetas"]] == ["mireceta_mis_lentejas"]
    assert [p.id for p in await context.store.get_products(USER)] == ["mireceta_mis_lentejas"]
