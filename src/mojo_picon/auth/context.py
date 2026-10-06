from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserContext:
    """Who is acting, created by the backend from a verified token (ADR-14, ADR-20).

    It reaches the tools as an injected argument and in LangGraph's runtime context, never in
    the model's prompt or in the graph state: the model cannot read or change it.
    """

    uid: str
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"user"}))
    timezone: str = "Atlantic/Canary"

    def __post_init__(self) -> None:
        if not self.uid or "/" in self.uid:
            raise ValueError("invalid uid")  # a uid is used in Firestore paths
