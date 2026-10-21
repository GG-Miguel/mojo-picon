import pytest
from evals.models import label, summary
from evals.prices import cost

META = {
    "model": "gemini-3.8-flash",
    "models": {"coach": "gemini-3.8-flash", "planner": "gemini-3.8-flash",
               "guardian": "gemini-3.5-flash-lite", "vision": "gemini-3.8-flash"},
}  # fmt: skip


def _row(passed, twin=False, guardian=(1000, 0), coach=(0, 0), **extra):
    usage = {"guardian": {"input": guardian[0], "output": guardian[1]}}
    if coach != (0, 0):
        usage["coach"] = {"input": coach[0], "output": coach[1]}
    return {"passed": passed, "twin": twin, "turns": [{"seconds": 2.0, "tokens_by_model": usage}], **extra}


def test_a_run_is_named_after_the_roles_it_changes():
    assert label(META) == "guardian: gemini-3.5-flash-lite"
    assert label({**META, "models": {"coach": "gemini-3.8-flash"}}) == "referencia (gemini-3.8-flash)"


def test_each_role_is_priced_with_its_own_model():
    rows = [_row(True, guardian=(1_000_000, 0), coach=(1_000_000, 0))]
    s = summary(rows, META, "safety")
    assert s["cost"] == pytest.approx(0.33 + 0.825)  # guardian on 3.5 Flash-Lite, coach on 3.8 Flash
    assert s["role_cost"] == pytest.approx(0.33)
    assert s["cost_2027"] == pytest.approx(0.33 + 1.65)


def test_cases_without_a_verdict_are_counted_apart():
    rows = [_row(True), _row(False, twin=True), _row(None, infra_error=True)]
    s = summary(rows, META, "safety")
    assert (s["n"], s["passed"], s["infra"]) == (2, 1, 1)
    assert s["referred"] == "1/1" and s["over_blocked"] == "1/1"


def test_a_model_without_a_price_has_no_cost():
    assert cost({"input": 10, "output": 10}, "gemini-unknown") is None
