import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from tests.fakes import FakeProvider, tool_call

from mojo_picon.agents import AgentContext, build_graph
from mojo_picon.agents.coach import MAX_COACH_STEPS
from mojo_picon.agents.planner import build_planner
from mojo_picon.auth import UserContext
from mojo_picon.domain import MacroTargets, Meal, Plan, PlanItem, Profile, Sex
from mojo_picon.guardrails.output import FEEDBACK_NAME
from mojo_picon.guardrails.responses import (
    NO_RELIABLE_FIGURE,
    SAFETY_BLOCK_RESPONSE,
    STEP_LIMIT_RESPONSE,
    WARNING_SENTENCE,
    fixed_response,
)
from mojo_picon.guardrails.rules import GuardDecision
from mojo_picon.llm import Role
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.energy import daily_target, load_met_table
from mojo_picon.tools.food_search import FoodIndex
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
USER = UserContext(uid="uid-7f3c")  # a uid that cannot appear by chance in Spanish text
PROFILE = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175)
OK = GuardDecision(level="ok", category="none")


@pytest.fixture
async def context():
    store = InMemoryStore()
    await store.save_profile(USER, PROFILE)
    return AgentContext(
        user=USER,
        store=store,
        foods=FOODS,
        food_index=FoodIndex(FOODS),
        activities=load_met_table(),
        profile=PROFILE,
    )


async def run(models, context, text):
    graph = build_graph(models, FOODS)
    return await graph.ainvoke({"messages": [HumanMessage(text)]}, context=context)


def final_text(state) -> str:
    return state["messages"][-1].text


def remaining_after_toast() -> int:
    # 60 g of home-made toast against the day's target, as the tools compute it
    target = daily_target(PROFILE).target.kcal
    return round(target - round(FOODS["pan_tostado_casero"].nutrients_for(60).kcal, 1))


def toast_script(final_answers: list[str]) -> list:
    return [
        tool_call("search_food", "c1", query="tostada"),
        tool_call("log_meal", "c2", items=[{"food_id": "pan_tostado_casero", "grams": 60}]),
        tool_call("get_day_balance", "c3"),
        *[AIMessage(a) for a in final_answers],
    ]


# --- input guardian -------------------------------------------------------------------


async def test_risky_message_gets_the_fixed_answer_without_any_llm(context):
    models = FakeProvider()  # no model is scripted: any call would fail
    state = await run(models, context, "Tengo diabetes tipo 1, ¿cuánta insulina me pongo antes de correr?")
    assert final_text(state) == fixed_response("medication")
    assert models.get(Role.GUARDIAN).calls == 0 and models.get(Role.COACH).calls == 0


async def test_classifier_can_derive_off_topic(context):
    models = FakeProvider(guardian=[GuardDecision(level="derivar", category="off_topic")])
    state = await run(models, context, "¿Quién ganó el partido de ayer?")
    assert final_text(state) == fixed_response("off_topic")
    assert models.get(Role.COACH).calls == 0


async def test_classifier_failure_falls_back_to_warning(context):
    models = FakeProvider(guardian=[ValueError("bad json")], coach=[AIMessage("Una cena ligera.")])
    state = await run(models, context, "¿Qué ceno?")
    assert state["guard_level"] == "aviso"
    assert final_text(state).endswith(WARNING_SENTENCE)


async def test_classifier_sees_the_previous_answer_as_context(context):
    models = FakeProvider(guardian=[OK], coach=[AIMessage("Anotado.")])
    graph = build_graph(models, FOODS)
    history = [
        HumanMessage("Me he tomado un batido con este polvo de proteína"),
        tool_call("search_food", query="proteína whey"),
        ToolMessage("guardado", tool_call_id="c1"),
        AIMessage("La etiqueta dice 78 g de proteína por 100 g. ¿Son correctos?"),
        HumanMessage("Sí. Me he tomado 30 g."),
    ]
    await graph.ainvoke({"messages": history}, context=context)
    prompt = models.get(Role.GUARDIAN).received[0][-1].text
    assert "¿Son correctos?" in prompt and prompt.index("contexto") < prompt.index("Me he tomado 30 g")


async def test_classifier_does_not_see_the_photo_analysis(context):
    models = FakeProvider(guardian=[OK], coach=[AIMessage("Lleva leche: con tu alergia, mejor no.")])
    data = "<datos_foto>\nATENCIÓN: milk está en las alergias del usuario.\n</datos_foto>"
    await run(models, context, f"¿Puedo tomarme esto?\n\n{data}")
    prompt = models.get(Role.GUARDIAN).received[0][-1].text
    assert "¿Puedo tomarme esto?" in prompt and "ATENCIÓN" not in prompt


async def test_first_turn_has_no_context(context):
    models = FakeProvider(guardian=[OK], coach=[AIMessage("Una cena ligera.")])
    await run(models, context, "¿Qué ceno?")
    assert "contexto" not in models.get(Role.GUARDIAN).received[0][-1].text


# --- Coach with tools and output guardian ----------------------------------------------


async def test_logs_a_meal_and_answers_with_numbers_from_the_tools(context):
    expected = remaining_after_toast()
    answer = f"He registrado 60 g de tostada. Te quedan {expected} kcal para hoy."
    models = FakeProvider(guardian=[OK], coach=toast_script([answer]))

    state = await run(models, context, "He desayunado dos tostadas")

    assert final_text(state) == answer
    assert [m.name for m in state["messages"] if isinstance(m, ToolMessage)] == [
        "search_food",
        "log_meal",
        "get_day_balance",
    ]
    assert len(await context.store.list_entries(USER, state_day(state))) == 1


def state_day(state):
    balance = json.loads(next(m for m in state["messages"] if m.name == "get_day_balance").text)
    return date.fromisoformat(balance["day"])


async def test_invented_number_is_regenerated_once(context):
    expected = remaining_after_toast()
    good = f"Te quedan {expected} kcal."
    models = FakeProvider(guardian=[OK], coach=toast_script(["Te quedan 2.500 kcal.", good]))

    state = await run(models, context, "He desayunado dos tostadas")

    assert final_text(state) == good
    assert state["output_attempts"] == 1
    feedback = [m for m in state["messages"] if isinstance(m, HumanMessage) and m.name == FEEDBACK_NAME]
    assert "2.500 kcal" in feedback[0].text


async def test_invented_number_twice_is_removed(context):
    models = FakeProvider(guardian=[OK], coach=toast_script(["Te quedan 2.500 kcal.", "Te quedan 3.000 kcal."]))
    state = await run(models, context, "He desayunado dos tostadas")
    assert final_text(state) == NO_RELIABLE_FIGURE


async def test_every_number_check_is_recorded(context):
    models = FakeProvider(guardian=[OK], coach=toast_script(["Te quedan 2.500 kcal.", "Te quedan 3.000 kcal."]))
    state = await run(models, context, "He desayunado dos tostadas")
    assert state["number_check"] == {"unsourced": ["3.000 kcal"], "action": "drop"}


async def test_without_the_number_checker_an_invented_number_reaches_the_user_and_is_recorded(context):
    """The variant the evaluation compares against: the guardian records, but does not correct."""
    models = FakeProvider(guardian=[OK], coach=toast_script(["Te quedan 2.500 kcal."]))
    graph = build_graph(models, FOODS, number_check=False)
    state = await graph.ainvoke({"messages": [HumanMessage("He desayunado dos tostadas")]}, context=context)
    assert final_text(state) == "Te quedan 2.500 kcal."
    assert "output_attempts" not in state
    assert state["number_check"] == {"unsourced": ["2.500 kcal"], "action": "off"}


async def test_without_guides_search_guides_cannot_run(context):
    models = FakeProvider(guardian=[OK], coach=[tool_call("search_guides", query="agua"), AIMessage("Bebe agua.")])
    graph = build_graph(models, FOODS, guides=False)
    state = await graph.ainvoke({"messages": [HumanMessage("¿Cuánta agua bebo?")]}, context=context)
    result = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert result.status == "error" and "search_guides" in result.text


async def test_warning_level_adds_the_recommendation(context):
    models = FakeProvider(guardian=[OK], coach=[AIMessage("Una cena ligera y bebe agua.")])
    state = await run(models, context, "Estoy algo resfriado, ¿qué ceno?")
    assert state["guard_level"] == "aviso"  # from the fast rules
    assert final_text(state) == "Una cena ligera y bebe agua.\n\n" + WARNING_SENTENCE


async def test_forbidden_advice_in_the_answer_is_replaced(context):
    models = FakeProvider(guardian=[OK], coach=[AIMessage("Ajusta la dosis de tu medicación antes de correr.")])
    state = await run(models, context, "¿Algo antes de correr?")
    assert "dosis" not in final_text(state)
    assert "profesional sanitario" in final_text(state)


async def test_gemini_safety_block_gives_a_neutral_answer(context):
    blocked = AIMessage("", response_metadata={"finish_reason": "SAFETY"})
    models = FakeProvider(guardian=[OK], coach=[blocked])
    state = await run(models, context, "…")
    assert final_text(state) == SAFETY_BLOCK_RESPONSE
    assert state["stop_reason"].startswith("safety_block")


async def test_coach_step_limit(context):
    loop = [tool_call("get_day_balance", f"c{i}") for i in range(MAX_COACH_STEPS)]
    models = FakeProvider(guardian=[OK], coach=loop)
    state = await run(models, context, "¿Cuánto me queda?")
    assert final_text(state) == STEP_LIMIT_RESPONSE
    assert state["stop_reason"] == "step_limit"


async def test_the_user_id_never_enters_the_state_or_the_prompts(context):
    expected = remaining_after_toast()
    models = FakeProvider(guardian=[OK], coach=toast_script([f"Te quedan {expected} kcal."]))
    state = await run(models, context, "He desayunado dos tostadas")
    assert USER.uid not in json.dumps(state, default=str)
    prompts = models.get(Role.COACH).received
    assert all(USER.uid not in m.text for call in prompts for m in call)


# --- Planner -----------------------------------------------------------------------------

DINNER = Plan(
    meals=[
        Meal(
            name="cena",
            items=[
                PlanItem(food_id="arroz_blanco_cocido", grams=150),
                PlanItem(food_id="pechuga_pollo_plancha", grams=150),
                PlanItem(food_id="aceite_oliva", grams=10),
            ],
        )
    ]
)
LOW_PROTEIN = Plan(meals=[Meal(name="cena", items=[PlanItem(food_id="arroz_blanco_cocido", grams=300)])])


def remaining_for(plan: Plan) -> MacroTargets:
    kcal = protein = carbs = fat = 0.0
    for item in plan.items:
        n = FOODS[item.food_id].nutrients_for(item.grams)
        kcal, protein, carbs, fat = kcal + n.kcal, protein + n.protein_g, carbs + n.carbs_g, fat + n.fat_g
    return MacroTargets(kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat)


async def test_planner_corrects_with_the_verifier_feedback():
    models = FakeProvider(planner=[LOW_PROTEIN, DINNER])
    planner = build_planner(models, FOODS)
    result = await planner.ainvoke({"meals": ["cena"], "remaining": remaining_for(DINNER), "allergens": []})
    assert result["passed"] and result["attempts"] == 2
    second_prompt = models.get(Role.PLANNER).received[1]
    assert "proteína" in second_prompt[-1].text  # the concrete error was fed back


async def test_planner_stops_after_three_attempts():
    models = FakeProvider(planner=[LOW_PROTEIN] * 3)
    planner = build_planner(models, FOODS)
    result = await planner.ainvoke({"meals": ["cena"], "remaining": remaining_for(DINNER), "allergens": []})
    assert not result["passed"] and result["attempts"] == 3


async def test_coach_delegates_planning_to_the_planner(context):
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("plan_rest_of_day", "p1", meals=["cena"]), AIMessage("No he encontrado un plan que cumpla.")],
        planner=[LOW_PROTEIN] * 3,
    )
    state = await run(models, context, "¿Qué ceno?")
    reply = next(m for m in state["messages"] if isinstance(m, ToolMessage) and m.name == "plan_rest_of_day")
    result = json.loads(reply.text)
    assert result["verificado"] is False and result["intentos"] == 3
    assert result["plan"][0]["alimentos"][0]["nombre"] == "Arroz blanco cocido"
    assert final_text(state) == "No he encontrado un plan que cumpla."


async def test_log_meal_returns_the_balance_after_writing(context):
    # Even if the model asks for the balance in parallel, the log result carries the fresh one
    expected = remaining_after_toast()
    models = FakeProvider(
        guardian=[OK],
        coach=[
            tool_call("log_meal", "c1", items=[{"food_id": "pan_tostado_casero", "grams": 60}]),
            AIMessage(f"Te quedan {expected} kcal."),
        ],
    )
    state = await run(models, context, "Dos tostadas")
    logged = json.loads(next(m for m in state["messages"] if isinstance(m, ToolMessage)).text)
    assert logged["balance_tras_registrar"]["remaining"]["kcal"] == expected
    assert final_text(state) == f"Te quedan {expected} kcal."


# --- review findings (2026-10-12) ---------------------------------------------------


async def test_tool_errors_go_back_to_the_model_instead_of_aborting(context):
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("log_activity", "c1", activity_id="quidditch", minutes=30), AIMessage("¿Qué deporte era?")],
    )
    state = await run(models, context, "He hecho deporte")
    error = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert error.status == "error" and "quidditch" in error.text
    assert final_text(state) == "¿Qué deporte era?"


async def test_a_meal_logged_without_profile_is_reported_not_crashed(context):
    no_profile = AgentContext(**{**context.__dict__, "store": InMemoryStore(), "profile": None})
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("log_meal", "c1", items=[{"food_id": "platano", "grams": 120}]), AIMessage("Apuntado.")],
    )
    state = await run(models, no_profile, "Un plátano")
    logged = json.loads(next(m for m in state["messages"] if isinstance(m, ToolMessage)).text)
    assert logged["balance_tras_registrar"] is None and logged["registrado"]["items"][0]["food_id"] == "platano"


async def test_planner_failure_returns_an_error_to_the_coach(context):
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("plan_rest_of_day", "p1", meals=["cena"]), AIMessage("Ahora no puedo planificar.")],
        planner=[RuntimeError("model down")],
    )
    state = await run(models, context, "¿Qué ceno?")
    reply = json.loads(next(m for m in state["messages"] if isinstance(m, ToolMessage)).text)
    assert "error" in reply
    assert final_text(state) == "Ahora no puedo planificar."


@pytest.mark.parametrize(
    "answer", ["Un vaso de leche aporta 250 mg de calcio.", "Una dosis de cafeína antes de correr va bien."]
)
def test_nutrition_figures_are_not_forbidden_advice(answer):
    from mojo_picon.guardrails.output import _FORBIDDEN
    from mojo_picon.tools.foods import normalize

    assert _FORBIDDEN.search(normalize(answer)) is None


@pytest.mark.parametrize(
    "answer", ["Ajusta la dosis de tu medicación antes de correr.", "Ponte 4 unidades de insulina antes."]
)
async def test_medication_advice_is_replaced(context, answer):
    models = FakeProvider(guardian=[OK], coach=[AIMessage(answer)])
    state = await run(models, context, "Pregunta")
    assert final_text(state) != answer and "profesional sanitario" in final_text(state)


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Quiero perder 5 kg esta semana", "derivar"),
        ("perder 10 kilos en 4 semanas", "derivar"),
        ("bajar 6 kg en 15 días", "derivar"),
        ("perder 5 kg en un mes y medio", "ok"),
        ("¿Qué dosis de cafeína tomo antes de correr?", "ok"),
    ],
)
def test_fast_rules_extreme_goals_and_caffeine(text, level):
    from mojo_picon.guardrails.rules import classify_by_rules

    assert classify_by_rules(text).level == level


async def test_an_unreadable_proposal_is_one_failed_attempt_not_a_failed_plan():
    # Seen with Gemini on 2026-10-16: the reasoning used up the output limit and the JSON was cut
    from langchain_core.exceptions import OutputParserException

    models = FakeProvider(planner=[OutputParserException("cut JSON"), DINNER])
    planner = build_planner(models, FOODS)
    result = await planner.ainvoke({"meals": ["cena"], "remaining": remaining_for(DINNER), "allergens": []})
    assert result["passed"] and result["attempts"] == 2
