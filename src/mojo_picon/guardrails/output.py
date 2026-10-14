"""Output guardian node: checks the Coach's final answer before it reaches the user.

1. Forbidden advice (medication, dosages): the answer is replaced by the fixed referral.
2. Numbers with origin (ADR-19): one regeneration with the concrete feedback; if it fails again,
   the sentences with unsourced numbers are removed.
3. "aviso" level: the recommendation to see a professional must be there; if not, it is added.

Nodes take the graph state as a dict and an unparametrised Runtime (runtime.context is an
AgentContext): guardrails/ does not import agents/, which builds the graph with these nodes.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from mojo_picon.guardrails.number_origin import TurnSources, check_numbers, drop_sentences, feedback
from mojo_picon.guardrails.responses import DEFAULT_REFERRAL, NO_RELIABLE_FIGURE, WARNING_SENTENCE
from mojo_picon.tools.foods import normalize

FEEDBACK_NAME = "output_guard"  # feedback messages to the Coach are HumanMessages with this name
# Retrieved passages count only when cited (state["sources"]), never as tool results: otherwise any
# number of a passage would pass without its citation (ADR-19).
RETRIEVAL_TOOL = "search_guides"
MAX_REGENERATIONS = 1
_DRUGS = (
    r"(insulina|metformina|medicamentos?|medicacion|farmacos?|pastillas?|antibioticos?|anticoagulantes?"
    r"|paracetamol|ibuprofeno|antidepresivos?)"
)
# Medication advice only: a dose word and a drug in the same stretch of text. «250 mg de calcio» or
# «una dosis de cafeína» are nutrition, not medication.
_FORBIDDEN = re.compile(
    rf"\b(dosis|unidades|ui|mg|ponte|inyectate|toma|ajusta|sube|baja)\b.{{0,30}}\b{_DRUGS}\b"
    rf"|\b{_DRUGS}\b.{{0,30}}\b(\d+\s*(ui|mg|unidades)|dosis)\b"
)
_PROFESSIONAL = re.compile(r"\b(profesional|medic[oa]|dietista|nutricionista|sanitari[oa])\b")


def turn_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Messages since the user's last message (feedback from this guardian does not start a turn)."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, HumanMessage) and m.name != FEEDBACK_NAME:
            return messages[i:]
    return messages


async def output_guard(state: dict, runtime: Runtime) -> dict:
    messages = state["messages"]
    answer = messages[-1]
    if not isinstance(answer, AIMessage):
        return {}
    text = answer.text
    norm = normalize(text)

    if _FORBIDDEN.search(norm):
        return {"messages": [AIMessage(content=DEFAULT_REFERRAL, id=answer.id)], "stop_reason": "forbidden_advice"}

    turn = turn_messages(messages)
    profile = runtime.context.profile
    sources = TurnSources(
        tool_results=[m.text for m in turn if isinstance(m, ToolMessage) and m.name != RETRIEVAL_TOOL],
        profile=profile.model_dump(mode="json") if profile else {},
        user_message=turn[0].text if turn else "",
        passages={**runtime.context.brief_passages, **state.get("sources", {})},
    )
    violations = check_numbers(text, sources)
    attempts = state.get("output_attempts", 0)
    if violations and attempts < MAX_REGENERATIONS:
        return {
            "messages": [HumanMessage(content=feedback(violations), name=FEEDBACK_NAME)],
            "output_attempts": attempts + 1,
        }
    if violations:
        text = drop_sentences(text, violations)
        if not text.strip() or text.strip() == NO_RELIABLE_FIGURE:
            text = NO_RELIABLE_FIGURE

    if state.get("guard_level") == "aviso" and not _PROFESSIONAL.search(normalize(text)):
        text = f"{text.rstrip()}\n\n{WARNING_SENTENCE}"

    if text != answer.text:
        return {"messages": [AIMessage(content=text, id=answer.id)]}
    return {}


def route_after_output_guard(state: dict) -> str:
    last = state["messages"][-1]
    return "coach" if isinstance(last, HumanMessage) and last.name == FEEDBACK_NAME else "end"
