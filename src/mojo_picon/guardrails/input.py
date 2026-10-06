"""Input guardian node: fast rules, then the LLM classifier; the stricter level wins.

If the classifier fails (invalid output, Gemini block), the turn continues as "aviso": the Coach
answers only with general guidance and a recommendation to see a professional. The fast rules
have already caught the clear "derivar" cases.

Nodes take the graph state as a dict and an unparametrised Runtime (runtime.context is an
AgentContext): guardrails/ does not import agents/, which builds the graph with these nodes.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from mojo_picon.guardrails.rules import GuardDecision, classify_by_rules, stricter
from mojo_picon.llm import ModelProvider, Role, SafetyBlockedError
from mojo_picon.prompts import load_prompt

log = logging.getLogger(__name__)
CLASSIFIER_FAILED = GuardDecision(level="aviso", category="classifier_failed", reason="fallback")


def last_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and message.name is None:
            return message.text
    return ""


def make_input_guard(models: ModelProvider):
    async def input_guard(state: dict) -> dict:
        text = last_user_text(state)
        decision = classify_by_rules(text)
        if decision.level != "derivar":
            decision = stricter(decision, await _classify(models, text))
        return {"guard_level": decision.level, "guard_category": decision.category}

    return input_guard


async def _classify(models: ModelProvider, text: str) -> GuardDecision:
    classifier = models.get(Role.GUARDIAN).with_structured_output(GuardDecision)
    try:
        result = await classifier.ainvoke(
            [SystemMessage(load_prompt("guardian")), HumanMessage(f"Mensaje del usuario:\n<<<\n{text}\n>>>")]
        )
    except SafetyBlockedError:
        return GuardDecision(level="derivar", category="safety_block", reason="gemini")
    except Exception:  # invalid structured output, network…: fail to the cautious level
        log.exception("guardian classifier failed")
        return CLASSIFIER_FAILED
    return result if isinstance(result, GuardDecision) else CLASSIFIER_FAILED
