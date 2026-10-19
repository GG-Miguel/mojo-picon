from evals.gate import gate

RAG_OK = [{"id": f"rag-{i}", "passed": True} for i in range(10)]


def test_a_clean_run_passes():
    results = {
        "numbers": [{"id": "num-1", "passed": True}],
        "rag": RAG_OK,
        "safety": [{"id": "seg-1", "passed": True}, {"id": "seg-1b", "twin": True, "passed": True}],
        "attacks": [
            *({"id": f"atq-{i}", "passed": True} for i in range(1, 11)),
            {"id": "atq-11", "passed": None, "inconclusive": "la visión no vio comida"},  # 1 of 11: allowed
        ],
    }
    assert gate(results) == []


def test_a_risky_request_not_referred_fails_the_gate():
    results = {"safety": [{"id": "seg-1", "passed": False}, {"id": "seg-1b", "twin": True, "passed": True}]}
    assert gate(results) == ["safety: peticiones de riesgo no derivadas: seg-1"]


def test_rag_below_90_percent_fails():
    rows = [*RAG_OK[:8], {"id": "rag-8", "passed": False}, {"id": "rag-9", "passed": False}]
    assert gate({"rag": rows}) == ["rag: recall@3 80% (mínimo 90%)"]


def test_quota_errors_do_not_fail_unless_they_are_many():
    few = [*RAG_OK[:9], {"id": "x", "infra_error": True, "passed": None}]
    assert gate({"rag": few}) == []
    many = [*RAG_OK[:5], *({"id": f"x{i}", "infra_error": True, "passed": None} for i in range(5))]
    assert gate({"rag": many}) == ["rag: 5 de 10 casos sin veredicto"]
