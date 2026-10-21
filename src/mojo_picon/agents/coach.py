"""Coach node: ReAct supervisor that talks to the user and decides which tool to use."""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.runtime import Runtime

from mojo_picon.agents.state import AgentContext, CoachState
from mojo_picon.agents.tools import COACH_TOOLS
from mojo_picon.guardrails.responses import SAFETY_BLOCK_RESPONSE, STEP_LIMIT_RESPONSE
from mojo_picon.llm import ModelProvider, Role, SafetyBlockedError, ensure_not_blocked
from mojo_picon.prompts import load_prompt

MAX_COACH_STEPS = 12  # Observabilidad y límites


def coach_system_prompt(context: AgentContext, guard_level: str) -> str:
    """Stable prefix first (prompt + expert brief, cached), then what changes per turn."""
    parts = [load_prompt("coach")]
    if context.expert_brief:
        parts.append("## Ficha experta (cita sus etiquetas de fuente)\n" + context.expert_brief)
    if context.profile:
        p = context.profile
        allergens = ", ".join(sorted(a.value for a in p.allergens)) or "ninguno"
        parts.append(
            "## Perfil del usuario\n"
            f"Edad {p.age}, sexo {p.sex.value}, peso {p.weight_kg:g} kg, altura {p.height_cm:g} cm, "
            f"objetivo {p.goal.value}, alérgenos: {allergens}."
        )
    else:
        parts.append("## Perfil del usuario\nTodavía no hay perfil: pregunta solo los datos que falten.")
    if guard_level == "aviso":
        parts.append(
            "## Nivel de seguridad: aviso\nDa solo pautas generales y recomienda consultar a un profesional sanitario."
        )
    return "\n\n".join(parts)


def make_coach(models: ModelProvider, tools=COACH_TOOLS):
    async def coach(state: CoachState, runtime: Runtime[AgentContext]) -> dict:
        steps = state.get("iterations", 0)
        if steps >= MAX_COACH_STEPS:
            return {"messages": [AIMessage(STEP_LIMIT_RESPONSE)], "stop_reason": "step_limit"}
        model = models.get(Role.COACH).bind_tools(tools)
        prompt = [SystemMessage(coach_system_prompt(runtime.context, state.get("guard_level", "ok")))]
        try:
            response = ensure_not_blocked(await model.ainvoke(prompt + state["messages"]))
        except SafetyBlockedError as e:
            return {"messages": [AIMessage(SAFETY_BLOCK_RESPONSE)], "stop_reason": f"safety_block: {e.reason}"}
        return {"messages": [response], "iterations": steps + 1}

    return coach
