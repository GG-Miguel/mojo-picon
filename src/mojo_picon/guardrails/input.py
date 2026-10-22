"""Input guardian node: fast rules, then the LLM classifier; the stricter level wins.

The classifier also sees the assistant's previous answer, as context only: a short reply such as
"Me he tomado 30 g" after a product label is a meal, not a dose. The fast rules see only the user.

If the classifier fails (invalid output, Gemini block), the turn continues as "aviso": the Coach
answers only with general guidance and a recommendation to see a professional. The fast rules
have already caught the clear "derivar" cases.

Nodes take the graph state as a dict and an unparametrised Runtime (runtime.context is an
AgentContext): guardrails/ does not import agents/, which builds the graph with these nodes.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mojo_picon.guardrails.rules import GuardDecision, classify_by_rules, stricter
from mojo_picon.llm import ModelProvider, Role, SafetyBlockedError
from mojo_picon.prompts import load_prompt

log = logging.getLogger(__name__)
CLASSIFIER_FAILED = GuardDecision(level="aviso", category="classifier_failed", reason="fallback")
CONTEXT_CHARS = 600  # the end of the previous answer, where its question to the user usually is


def last_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and message.name is None:
            return message.text
    return ""


def previous_answer(state: dict) -> str:
    """The assistant's last answer before the user's last message ("" on the first turn)."""
    messages = state.get("messages", [])
    users = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage) and m.name is None]
    for message in reversed(messages[: users[-1]] if users else []):
        if isinstance(message, AIMessage) and not message.tool_calls and message.text.strip():
            return message.text[-CONTEXT_CHARS:]
    return ""


def make_input_guard(models: ModelProvider):
    async def input_guard(state: dict) -> dict:
        text = last_user_text(state)
        decision = classify_by_rules(text)
        if decision.level != "derivar":
            decision = stricter(decision, await _classify(models, text, previous_answer(state)))
        return {"guard_level": decision.level, "guard_category": decision.category}

    return input_guard


async def _classify(models: ModelProvider, text: str, context: str = "") -> GuardDecision:
    classifier = models.get(Role.GUARDIAN).with_structured_output(GuardDecision)
    prompt = f"Mensaje del usuario:\n<<<\n{_quoted(text)}\n>>>"
    if context:
        prompt = f"Respuesta anterior del asistente (solo contexto):\n<<<\n{_quoted(context)}\n>>>\n\n{prompt}"
    try:
        result = await classifier.ainvoke([SystemMessage(load_prompt("guardian")), HumanMessage(prompt)])
    except SafetyBlockedError:
        return GuardDecision(level="derivar", category="safety_block", reason="gemini")
    except Exception:  # invalid structured output, network…: fail to the cautious level
        log.exception("guardian classifier failed")
        return CLASSIFIER_FAILED
    return result if isinstance(result, GuardDecision) else CLASSIFIER_FAILED


def _quoted(text: str) -> str:
    """The message between the classifier's delimiters, which it cannot close from inside."""
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››")
