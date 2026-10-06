"""Scripted chat models for testing the graph without calling Gemini."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from mojo_picon.llm import Role


class ScriptedChatModel(BaseChatModel):
    """Returns the scripted answers in order: AIMessages for chat calls, objects (or exceptions)
    for structured-output calls. Records the messages it received."""

    script: list[Any] = Field(default_factory=list)
    received: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _next(self) -> Any:
        if not self.script:
            raise AssertionError("the model was called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.received.append(list(messages))
        message = self._next()
        assert isinstance(message, AIMessage), f"expected an AIMessage in the script, got {message!r}"
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        def answer(messages):
            self.received.append(list(messages))
            return self._next()

        return RunnableLambda(answer)

    @property
    def calls(self) -> int:
        return len(self.received)


class FakeProvider:
    def __init__(self, **scripts: list[Any]):
        self.models = {role: ScriptedChatModel(script=list(scripts.get(role.value, []))) for role in Role}

    def get(self, role: Role) -> ScriptedChatModel:
        return self.models[role]


def tool_call(name: str, call_id: str = "c1", **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])
