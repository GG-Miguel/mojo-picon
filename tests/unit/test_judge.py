import pytest

pytest.importorskip("deepeval")  # the eval group; the CI unit tests run without it

from evals.judge import GroqJudge, VertexJudge, make_judge


def test_the_judge_is_chosen_by_an_environment_variable(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("JUDGE", "groq")
    judge = make_judge()
    assert isinstance(judge, GroqJudge) and not isinstance(judge, VertexJudge)
    assert judge.get_model_name() == "openai/gpt-oss-120b (Groq)"
    monkeypatch.setenv("JUDGE", "other")
    with pytest.raises(ValueError):
        make_judge()


def test_vertex_serves_the_same_model_with_the_project_credentials(monkeypatch):
    import google.auth

    monkeypatch.setattr(google.auth, "default", lambda scopes: (object(), "mojo-picon"))
    monkeypatch.delenv("JUDGE", raising=False)
    judge = make_judge()
    assert isinstance(judge, VertexJudge)
    assert judge.get_model_name() == "openai/gpt-oss-120b-maas (Vertex AI)"
    assert "/projects/mojo-picon/locations/global/" in judge._url
