import pytest

from mojo_picon.config import Settings
from mojo_picon.devtools import require_development


def test_defaults_point_to_the_eu_endpoint_and_the_project(monkeypatch):
    for name in ["ENVIRONMENT", "GCP_PROJECT_ID", "VERTEX_LOCATION", "GEMINI_MODEL", "LANGFUSE_PUBLIC_KEY"]:
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.gcp_project_id == "mojo-picon"
    assert settings.vertex_location == "eu" and "eu.rep" in settings.vertex_endpoint
    assert not settings.langfuse_enabled and not settings.is_production


def test_dev_tokens_are_parsed(monkeypatch):
    monkeypatch.setenv("API_DEV_TOKENS", "tok-a:ana, tok-y:yolanda,broken")
    assert Settings.from_env().api_dev_tokens == {"tok-a": "ana", "tok-y": "yolanda"}


def test_development_helpers_refuse_production():
    with pytest.raises(RuntimeError):
        require_development(Settings(environment="production"), "x")
