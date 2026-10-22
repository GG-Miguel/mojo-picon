"""The turn graph (Agentes: Flujo de un turno).

START -> input_guard -(derivar)-> fixed_response -> END
                     -(ok/aviso)-> coach <-> tools
                                   coach <-> planner (plan_rest_of_day)
                                   coach -> output_guard -(feedback)-> coach
                                                         -> END
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from mojo_picon.agents.coach import make_coach
from mojo_picon.agents.planner import build_planner
from mojo_picon.agents.state import AgentContext, CoachState
from mojo_picon.agents.tools import COACH_TOOLS, PLAN_TOOL
from mojo_picon.guardrails.input import make_input_guard
from mojo_picon.guardrails.output import make_output_guard, route_after_output_guard
from mojo_picon.guardrails.responses import fixed_response
from mojo_picon.llm import ModelProvider
from mojo_picon.tools import diary
from mojo_picon.tools.energy import planning_targets

log = logging.getLogger(__name__)


def fixed_response_node(state: CoachState) -> dict:
    """«derivar»: a pre-written answer, without calling any LLM."""
    return {"messages": [AIMessage(fixed_response(state.get("guard_category", "")))]}


def make_planner_node(models: ModelProvider, foods):
    planner = build_planner(models, foods)

    async def planner_node(state: CoachState, runtime: Runtime[AgentContext]) -> dict:
        ctx = runtime.context
        call_message = state["messages"][-1]
        replies = []
        for call in call_message.tool_calls:
            if call["name"] != PLAN_TOOL:
                content = "No ejecutada: llama a plan_rest_of_day sola en un paso."
            else:
                content = await _plan(planner, ctx, call["args"])
            replies.append(ToolMessage(content=content, tool_call_id=call["id"], name=call["name"]))
        return {"messages": replies}

    return planner_node


async def _plan(planner, ctx: AgentContext, args: dict) -> str:
    """Always returns a JSON answer for the Coach, even when planning fails."""
    try:
        return await _run_planner(planner, ctx, args)
    except diary.ProfileMissingError:
        return json.dumps({"error": "no hay perfil: pregunta los datos del usuario"}, ensure_ascii=False)
    except Exception:
        log.exception("planner failed")
        return json.dumps({"error": "no he podido planificar ahora; dilo con honestidad"}, ensure_ascii=False)


async def _run_planner(planner, ctx: AgentContext, args: dict) -> str:
    balance = await diary.get_day_balance(ctx.user, ctx.store)
    targets, notes = planning_targets(balance.remaining)
    result = await planner.ainvoke(
        {
            "meals": args.get("meals") or ["cena"],
            "preferences": args.get("preferences", ""),
            "remaining": targets,
            "allergens": sorted(ctx.profile.allergens) if ctx.profile else [],
        }
    )
    plan = result.get("plan")
    meals = [
        {
            "comida": meal.name,
            "alimentos": [{"food_id": i.food_id, "nombre": ctx.foods[i.food_id].name, "gramos": i.grams}
                          for i in meal.items if i.food_id in ctx.foods],
        }
        for meal in (plan.meals if plan else [])
    ]  # fmt: skip
    totals = {}
    if plan:
        totals = _totals(ctx, plan)
    return json.dumps(
        {
            "verificado": result.get("passed", False),
            "intentos": result.get("attempts", 0),
            "problemas": result.get("issues", []),
            "plan": meals,
            "total_plan": totals,
            "quedaba": balance.remaining.model_dump(),
            "objetivo_del_plan": targets.model_dump(),
            "avisos": notes,
        },
        ensure_ascii=False,
    )


def _totals(ctx: AgentContext, plan) -> dict:
    kcal = protein = carbs = fat = 0.0
    for item in plan.items:
        food = ctx.foods.get(item.food_id)
        if food:
            n = food.nutrients_for(item.grams)
            kcal, protein, carbs, fat = kcal + n.kcal, protein + n.protein_g, carbs + n.carbs_g, fat + n.fat_g
    return {"kcal": round(kcal), "protein_g": round(protein), "carbs_g": round(carbs), "fat_g": round(fat)}


def route_after_input_guard(state: CoachState) -> str:
    return "fixed_response" if state.get("guard_level") == "derivar" else "coach"


def route_after_coach(state: CoachState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        if any(call["name"] == PLAN_TOOL for call in last.tool_calls):
            return "planner"
        return "tools"
    return "output_guard"


def build_graph(models: ModelProvider, foods, *, guides: bool = True, number_check: bool = True):
    """The production graph. `guides=False` (no search_guides) and `number_check=False` (the output
    guardian only records) are the variants the evaluation compares against (Evidencias para la memoria)."""
    tools = [t for t in COACH_TOOLS if guides or t.name != "search_guides"]
    graph = StateGraph(CoachState, context_schema=AgentContext)
    graph.add_node("input_guard", make_input_guard(models))
    graph.add_node("fixed_response", fixed_response_node)
    graph.add_node("coach", make_coach(models, tools))
    # Any tool error goes back to the model as a ToolMessage (it can correct the call or tell the
    # user); it never aborts the turn.
    graph.add_node("tools", ToolNode([t for t in tools if t.name != PLAN_TOOL], handle_tool_errors=True))
    graph.add_node("planner", make_planner_node(models, foods))
    graph.add_node("output_guard", make_output_guard(number_check))

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard", route_after_input_guard, {"fixed_response": "fixed_response", "coach": "coach"}
    )
    graph.add_edge("fixed_response", END)
    graph.add_conditional_edges(
        "coach", route_after_coach, {"tools": "tools", "planner": "planner", "output_guard": "output_guard"}
    )
    graph.add_edge("tools", "coach")
    graph.add_edge("planner", "coach")
    graph.add_conditional_edges("output_guard", route_after_output_guard, {"coach": "coach", "end": END})
    return graph.compile()
