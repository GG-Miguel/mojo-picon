"""Graph state of one turn, and the read-only runtime context (Agentes: Estado del turno).

The state lives only during the turn; between turns the backend stores what is needed in the
session (ADR-18). The UserContext and the data access are in the runtime context, never in the
state or the prompt: the model cannot read or change them (ADR-14, ADR-20).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from mojo_picon.auth.context import UserContext
from mojo_picon.domain import Food, Profile
from mojo_picon.rag.index import GuideSearch
from mojo_picon.store.base import Store
from mojo_picon.tools.energy import MetActivity
from mojo_picon.tools.food_search import FoodIndex

GuardLevel = Literal["ok", "aviso", "derivar"]


def merge_sources(old: dict[str, str] | None, new: dict[str, str] | None) -> dict[str, str]:
    """Passages of several searches in the same turn (also in parallel tool calls) add up."""
    return {**(old or {}), **(new or {})}


class CoachState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # current turn + summary of earlier ones
    guard_level: GuardLevel
    guard_category: str
    sources: Annotated[dict[str, str], merge_sources]  # retrieved passages, by citation tag (numbers with origin)
    iterations: int  # Coach steps in this turn (limit: MAX_COACH_STEPS)
    output_attempts: int  # regenerations asked by the output guardian
    stop_reason: str  # why the turn stopped early, if it did (logged)


@dataclass(frozen=True)
class AgentContext:
    """LangGraph runtime context: who the user is and how to reach their data."""

    user: UserContext
    store: Store
    foods: Mapping[str, Food]
    food_index: FoodIndex
    activities: Mapping[str, MetActivity]
    profile: Profile | None = None  # loaded by the backend at the start of the turn
    expert_brief: str = ""  # cached prefix of the Coach's prompt (ADR-23)
    brief_passages: Mapping[str, str] = field(default_factory=dict)  # citation tag -> line of the brief
    guides: GuideSearch | None = None  # guideline index (RAG); None: expert brief only
