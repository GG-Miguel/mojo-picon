from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from mojo_picon.config import Settings
from mojo_picon.llm import (
    GeminiProvider,
    LiteLLMProvider,
    Role,
    SafetyBlockedError,
    ensure_not_blocked,
    model_provider,
)


def _deployments(provider: LiteLLMProvider, role: Role) -> dict[str, dict]:
    router = provider.get(role).router
    return {d["model_name"]: d["litellm_params"] for d in router.model_list}


def test_the_gateway_tries_gemini_then_claude_on_the_eu_endpoint():
    provider = LiteLLMProvider.from_settings(Settings())
    deployments = _deployments(provider, Role.COACH)
    assert deployments["coach"]["model"] == "vertex_ai/gemini-3.8-flash"
    assert deployments["coach"]["vertex_location"] == "eu"
    assert deployments["coach-fallback"]["model"] == "vertex_ai/claude-haiku-4-5@20251001"
    assert deployments["coach-fallback"]["vertex_location"] == "eu"
    assert provider.get(Role.COACH).router.fallbacks == [{"coach": ["coach-fallback"]}]


def test_limits_apply_to_both_models_and_only_gemini_gets_the_thinking_level():
    deployments = _deployments(LiteLLMProvider.from_settings(Settings()), Role.GUARDIAN)
    for params in deployments.values():
        assert params["timeout"] == 20 and params["max_tokens"] == 1024 and params["temperature"] == 0.0
    assert deployments["guardian"]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in deployments["guardian-fallback"]  # Claude would think and bill for it


def test_without_a_fallback_model_gemini_answers_alone():
    provider = LiteLLMProvider.from_settings(replace(Settings(), fallback_model=""))
    assert list(_deployments(provider, Role.PLANNER)) == ["planner"]


def test_direct_mode_skips_the_gateway():
    assert isinstance(model_provider(replace(Settings(), llm_gateway="direct")), GeminiProvider)
    assert isinstance(model_provider(Settings()), LiteLLMProvider)


def test_a_safety_block_reported_by_litellm_is_still_a_block():
    blocked = AIMessage(content="", response_metadata={"finish_reason": "content_filter"})
    with pytest.raises(SafetyBlockedError):
        ensure_not_blocked(blocked)
