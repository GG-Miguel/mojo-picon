"""Planner subgraph: propose -> verify_plan -> correct, at most MAX_PLANNER_ATTEMPTS times.

Its loop has steps the Coach does not need: it is isolated and limited separately (ADR-02).
The LLM only chooses foods and grams; every number is checked by verify_plan (ADR-05).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TypedDict

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from mojo_picon.domain import Allergen, Food, MacroTargets, Plan
from mojo_picon.llm import ModelProvider, Role
from mojo_picon.prompts import load_prompt
from mojo_picon.tools.verify_plan import verify_plan

log = logging.getLogger(__name__)
MAX_PLANNER_ATTEMPTS = 3


class PlannerState(TypedDict, total=False):
    meals: list[str]
    preferences: str
    remaining: MacroTargets
    allergens: list[Allergen]
    plan: Plan | None
    issues: list[str]
    passed: bool
    attempts: int


def catalogue(foods: Mapping[str, Food], allergens: frozenset[Allergen]) -> str:
    """Foods the planner may use (without the user's allergens), one per line."""
    return "\n".join(
        f"{f.id}: {f.name} (máx. {f.max_portion_g:g} g)" for f in foods.values() if not f.allergens & allergens
    )


def build_planner(models: ModelProvider, foods: Mapping[str, Food]):
    async def propose(state: PlannerState) -> dict:
        allergens = frozenset(state.get("allergens", []))
        remaining = state["remaining"]
        request = (
            f"Comidas: {', '.join(state['meals'])}.\n"
            f"Queda para hoy: {remaining.kcal:g} kcal, proteína {remaining.protein_g:g} g, "
            f"hidratos {remaining.carbs_g:g} g, grasas {remaining.fat_g:g} g.\n"
            f"Alérgenos del usuario: {', '.join(a.value for a in allergens) or 'ninguno'}.\n"
            f"Preferencias: {state.get('preferences') or 'ninguna'}.\n\n"
            f"Catálogo (food_id: nombre):\n{catalogue(foods, allergens)}"
        )
        messages = [SystemMessage(load_prompt("planner")), HumanMessage(request)]
        if state.get("plan") and state.get("issues"):
            messages.append(
                HumanMessage(
                    "Tu propuesta anterior:\n"
                    + state["plan"].model_dump_json()
                    + "\nErrores del verificador:\n- "
                    + "\n- ".join(state["issues"])
                )
            )
        try:
            plan = await models.get(Role.PLANNER).with_structured_output(Plan).ainvoke(messages)
        except OutputParserException:  # unreadable or cut output: one failed attempt, not a failed plan
            log.warning("planner proposal could not be parsed", exc_info=True)
            plan = None
        return {"plan": plan if isinstance(plan, Plan) else None, "attempts": state.get("attempts", 0) + 1}

    def verify(state: PlannerState) -> dict:
        if state.get("plan") is None:
            return {"passed": False, "issues": ["la propuesta no tenía el formato pedido"]}
        result = verify_plan(state["plan"], state["remaining"], frozenset(state.get("allergens", [])), foods)
        return {"passed": result.passed, "issues": [i.message for i in result.issues]}

    def next_step(state: PlannerState) -> str:
        if state["passed"] or state["attempts"] >= MAX_PLANNER_ATTEMPTS:
            return "end"
        return "propose"

    graph = StateGraph(PlannerState)
    graph.add_node("propose", propose)
    graph.add_node("verify", verify)
    graph.add_edge(START, "propose")
    graph.add_edge("propose", "verify")
    graph.add_conditional_edges("verify", next_step, {"propose": "propose", "end": END})
    return graph.compile()
