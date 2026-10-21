import pytest
from evals.harness import VARIANTS, Harness, asks_user

from mojo_picon.config import Settings


@pytest.mark.parametrize(
    ("answer", "asks"),
    [
        ("¿Cuántos ml tenía cada caña?", True),
        ("Dime la cantidad que prefieras y te las registro.", True),  # conv-10, 18 Oct: no question mark
        ("Necesito saber cuántos gramos fueron.", True),
        ("Me indicas el aceite que usaste y lo apunto.", True),
        ("He registrado las dos cañas de cerveza (400 ml).", False),
        ("Te indico lo que dicen las guías.", False),
        ("Registrado: 1 manzana (168 g). Si el tamaño era diferente, dímelo y lo ajustamos.", False),  # conv-14
    ],
)
def test_the_simulated_user_answers_questions_and_requests(answer, asks):
    assert asks_user(answer) is asks


def test_the_harness_runs_the_agent_as_production_with_the_expert_brief(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY", "direct")  # no LiteLLM router to build; no model is called
    complete = Harness(Settings.from_env())
    assert complete.brief and complete.brief_passages
    without = Harness(Settings.from_env(), VARIANTS["sin_ficha"])
    assert without.brief == "" and without.brief_passages == {}
