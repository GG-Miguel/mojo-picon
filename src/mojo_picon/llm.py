"""Single access point to the models: get_model(role) (ADR-20).

Today it returns Gemini on Vertex AI (EU region); in milestone 3 it points to LiteLLM by
changing only this module's configuration. Tests inject a provider with fake models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage


class Role(StrEnum):
    COACH = "coach"
    PLANNER = "planner"
    GUARDIAN = "guardian"
    VISION = "vision"


# Low temperature where the output feeds code (planner, guardian, vision).
TEMPERATURES = {Role.COACH: 0.4, Role.PLANNER: 0.2, Role.GUARDIAN: 0.0, Role.VISION: 0.0}
# Gemini counts its reasoning tokens inside this limit: on 2026-10-16 the planner used 1400-1960
# of 2048 tokens reasoning and half of its plans arrived cut (MAX_TOKENS). The limit only stops
# a runaway answer; tokens are billed as used either way.
MAX_OUTPUT_TOKENS = {Role.COACH: 4096, Role.PLANNER: 8192, Role.GUARDIAN: 1024, Role.VISION: 4096}
# Nothing without a limit (Principles): a slow endpoint fails the call instead of hanging the turn.
# Seen on 2026-10-14: the EU endpoint took 60-130 s per call, or never answered.
TIMEOUT_SECONDS = {Role.COACH: 45, Role.PLANNER: 60, Role.GUARDIAN: 20, Role.VISION: 45}
MAX_RETRIES = 1
# Reasoning tokens are billed as output (14 Oct: ~2/3 of the day's output tokens). Only where the task
# needs little reasoning: the guardian classifies. Roles not listed keep the model's default.
THINKING = {Role.GUARDIAN: "low"}


def thinking_config(model: str, level: str) -> dict:
    """Thinking settings for the model family: Gemini 3 takes a level; Gemini 2.5 rejects levels and
    takes a token budget (0 turns thinking off on Flash)."""
    if model.startswith("gemini-2"):
        return {"thinking_budget": 0 if level == "low" else -1}  # -1: dynamic, the model decides
    return {"thinking_level": level}


class ModelProvider(Protocol):
    def get(self, role: Role) -> BaseChatModel: ...


class SafetyBlockedError(Exception):
    """Gemini blocked the input or the output: there is no error, just an empty answer with a reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class GeminiProvider:
    """Gemini on Vertex AI (Application Default Credentials).

    Defaults (config.Settings): the Vertex AI EU multi-region endpoint, for data residency in the
    EU (Principles #8). Checked on 2026-10-12: gemini-3.8-flash is served there and on
    "global"/us-central1, but not on the europe-west1 or europe-west4 regional endpoints.
    """

    def __init__(self, project: str, location: str, endpoint: str, model: str):
        self._project = project
        self._location = location
        self._endpoint = endpoint
        self._model = model
        self._cache: dict[Role, BaseChatModel] = {}

    @classmethod
    def from_settings(cls, settings) -> GeminiProvider:
        return cls(settings.gcp_project_id, settings.vertex_location, settings.vertex_endpoint, settings.gemini_model)

    def get(self, role: Role) -> BaseChatModel:
        if role not in self._cache:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._cache[role] = ChatGoogleGenerativeAI(
                model=self._model,
                vertexai=True,
                project=self._project,
                location=self._location,
                base_url=self._endpoint,
                temperature=TEMPERATURES[role],
                max_output_tokens=MAX_OUTPUT_TOKENS[role],
                timeout=TIMEOUT_SECONDS[role],
                max_retries=MAX_RETRIES,
                **({"thinking_config": thinking_config(self._model, THINKING[role])} if role in THINKING else {}),
            )
        return self._cache[role]


def gemini_embeddings(settings):
    """gemini-embedding-2 on the Vertex AI EU endpoint (RAG; ADR-04), whatever the chat model's region."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.embedding_location,
        base_url=settings.embedding_endpoint,
        request_options={"timeout": 20},
    )


def ensure_not_blocked(message: AIMessage) -> AIMessage:
    """Raise SafetyBlockedError if Gemini's safety filters blocked this call (Guardrails spec)."""
    metadata = message.response_metadata or {}
    finish_reason = str(metadata.get("finish_reason", "")).upper()
    feedback = metadata.get("prompt_feedback") or {}
    block_reason = feedback.get("block_reason") if isinstance(feedback, dict) else None
    if block_reason and str(block_reason).upper() not in ("0", "BLOCK_REASON_UNSPECIFIED"):
        raise SafetyBlockedError(f"input blocked: {block_reason}")
    if finish_reason.endswith("SAFETY") or finish_reason in ("PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        raise SafetyBlockedError(f"output blocked: {finish_reason}")
    return message
