"""Langfuse tracing (OpenTelemetry): one trace per turn, with user and session (Observabilidad).

Without LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY tracing is off (NullTracer), so tests and local
runs do not need an account. Images never reach the traces (the vision call disables input
capture); personal data masking with Presidio comes in milestone 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TurnTrace:
    callbacks: list[Any] = field(default_factory=list)  # LangChain callbacks for this turn
    url: str | None = None  # link shown next to the answer in the web
    trace_id: str | None = None


class Tracer(Protocol):
    def turn(self, user_id: str, session_id: str, user_input: str) -> Any:
        """Async context manager yielding a TurnTrace."""
        ...

    def event(self, name: str, metadata: dict[str, Any]) -> None: ...

    async def forget_user(self, user_id: str) -> int:
        """Delete every trace of a user (right to erasure); returns how many."""
        ...


class NullTracer:
    @asynccontextmanager
    async def turn(self, user_id: str, session_id: str, user_input: str) -> AsyncIterator[TurnTrace]:
        yield TurnTrace()

    def event(self, name: str, metadata: dict[str, Any]) -> None:
        pass

    async def forget_user(self, user_id: str) -> int:
        return 0


class LangfuseTracer:
    def __init__(self, environment: str):
        from langfuse import Langfuse

        self._client = Langfuse(environment=environment)

    @asynccontextmanager
    async def turn(self, user_id: str, session_id: str, user_input: str) -> AsyncIterator[TurnTrace]:
        from langfuse import propagate_attributes
        from langfuse.langchain import CallbackHandler

        with (
            self._client.start_as_current_observation(name="turn", as_type="agent", input=user_input) as span,
            propagate_attributes(user_id=user_id, session_id=session_id, trace_name="chat-turn"),
        ):
            trace_id = self._client.get_current_trace_id()
            trace = TurnTrace(
                callbacks=[CallbackHandler()], url=self._client.get_trace_url(trace_id=trace_id), trace_id=trace_id
            )
            yield trace
            span.update(output="(see the final message of the graph)")

    def event(self, name: str, metadata: dict[str, Any]) -> None:
        self._client.create_event(name=name, metadata=metadata)

    async def forget_user(self, user_id: str) -> int:
        """Every trace with this user id, deleted in batches (the traces carry the uid, never the email)."""
        # All the ids first, page by page: Langfuse deletes asynchronously, so listing again after a
        # delete could return the same traces and never end.
        ids: list[str] = []
        page_number = 1
        while True:
            page = await self._client.async_api.trace.list(user_id=user_id, page=page_number, limit=100, fields="core")
            ids += [t.id for t in page.data]
            if page_number >= page.meta.total_pages:
                break
            page_number += 1
        for start in range(0, len(ids), 100):
            await self._client.async_api.trace.delete_multiple(trace_ids=ids[start : start + 100])
        return len(ids)


def tracer_from_settings(settings) -> Tracer:
    """Langfuse reads its keys and host from LANGFUSE_* environment variables."""
    return LangfuseTracer(environment=settings.environment) if settings.langfuse_enabled else NullTracer()
