from dataclasses import asdict

import pytest

from mojo_picon.guardrails.number_origin import (
    Kind,
    TurnSources,
    check_numbers,
    classify,
    drop_sentences,
    extract_quantities,
    index_brief,
    parse_number,
    split_sentences,
)
from mojo_picon.tools.energy import per_kg_target

BRIEF = """\
## Proteína
- Deportistas de resistencia: 1,2–2 g/kg de proteína al día [ISSN 2017, §3]
- Repartir en tomas de 20–40 g cada 3–4 horas [ISSN 2017, §4]
## Hidratación
- Beber 400–600 ml en las 2 horas previas al ejercicio [ACSM 2016, §2]
"""

SOURCES = TurnSources(
    tool_results=[
        {"tool": "activity_energy", "kcal": 619.6},
        {"tool": "daily_balance", "consumed_kcal": 1400, "remaining_kcal": 1020, "protein_g_remaining": 58},
    ],
    profile={"weight_kg": 70, "age": 34},
    user_message="Esta tarde corro 10 km, ¿cuánta proteína debería tomar?",
    passages=index_brief(BRIEF),
)


# --- parsing -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"), [("1.400", 1400), ("1,2", 1.2), ("1.5", 1.5), ("12.000,5", 12000.5), ("620", 620)]
)
def test_parse_number_spanish_format(text, value):
    assert parse_number(text) == value


def test_extracts_ranges_units_and_word_numbers():
    qs = extract_quantities("Toma entre 1,2 y 2 g/kg. Bebe medio litro. Te quedan 1.020 kcal.")
    assert [(q.low, q.high, q.unit) for q in qs] == [(1.2, 2.0, "g/kg"), (0.5, 0.5, "l"), (1020, 1020, "kcal")]


def test_ignores_citation_years_dates_times_and_list_markers():
    qs = extract_quantities("1. Cena a las 21:30 del 12 de octubre [ISSN 2017, §3].")
    assert qs == []


# --- classification --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cited", "kind"),
    [
        ("620 kcal", False, Kind.PERSONAL),
        ("30 g", False, Kind.PERSONAL),
        ("30 g", True, Kind.REFERENCE),
        ("1,2 g/kg", False, Kind.REFERENCE),
        ("500 ml", False, Kind.REFERENCE),
        ("10 km", False, Kind.IGNORED),
        ("3 comidas", False, Kind.IGNORED),
        ("620", False, Kind.PERSONAL),
    ],
)
def test_classify(text, cited, kind):
    (q,) = extract_quantities(text)
    assert classify(q, cited) is kind


# --- acceptance test of the plan (Guardrails#Plan de implementación) --------------


def test_acceptance_correct_answer_passes():
    answer = (
        "Como corres 10 km, hoy gastas unas 620 kcal más y te quedan 1.020 kcal. "
        "Las guías recomiendan 1,2–2 g/kg de proteína al día [ISSN 2017]. "
        "Para ti son unos 84–140 g. "
        "Bebe 400–600 ml en las 2 horas previas [ACSM 2016]."
    )
    sources = TurnSources(
        **{**SOURCES.__dict__, "tool_results": [*SOURCES.tool_results, asdict(per_kg_target(70, 1.2, 2))]}
    )
    assert check_numbers(answer, sources) == []


def test_acceptance_wrong_personal_number_fails():
    violations = check_numbers("Te quedan 700 kcal para hoy.", SOURCES)
    assert [(v.quantity.text, v.kind) for v in violations] == [("700 kcal", Kind.PERSONAL)]


def test_acceptance_uncited_reference_fails():
    violations = check_numbers("Toma 3 g/kg de proteína.", SOURCES)
    assert [(v.quantity.text, v.kind) for v in violations] == [("3 g/kg", Kind.REFERENCE)]


def test_reference_must_be_in_the_cited_passage():
    # 1,2–2 g/kg exists in [ISSN 2017], not in [ACSM 2016]: wrong citation is rejected.
    assert check_numbers("Toma 1,2–2 g/kg de proteína [ISSN 2017].", SOURCES) == []
    assert len(check_numbers("Toma 1,2–2 g/kg de proteína [ACSM 2016].", SOURCES)) == 1


def test_personal_amount_from_brief_without_tool_fails():
    # "para ti 112 g" without calling per_kg_target: the brief does not validate personal figures.
    violations = check_numbers("Para ti son unos 112 g de proteína.", SOURCES)
    assert [v.kind for v in violations] == [Kind.PERSONAL]


def test_rounding_tolerance():
    assert check_numbers("Gastas 618 kcal corriendo.", SOURCES) == []
    assert len(check_numbers("Gastas 640 kcal corriendo.", SOURCES)) == 1


def test_numbers_written_by_the_user_are_accepted():
    sources = TurnSources(user_message="He comido 1.400 kcal y mañana corro 21 km")
    assert check_numbers("Con las 1.400 kcal que has comido, ¿cenamos ligero?", sources) == []


# --- fallback ---------------------------------------------------------------------


def test_drop_sentences_removes_whole_sentence():
    answer = "Te quedan 1.020 kcal. Toma 3 g/kg de proteína. ¡Ánimo con la carrera!"
    violations = check_numbers(answer, SOURCES)
    result = drop_sentences(answer, violations)
    assert "3 g/kg" not in result
    assert "Te quedan 1.020 kcal." in result
    assert result.endswith("No tengo un dato fiable para darte alguna de las cifras que me pedías.")


def test_tool_results_in_json_keep_list_numbers_and_decimals():
    tool = '{"items": [{"food_id": "x", "grams": 60.0}], "nutrients": {"kcal": 60.125}}'
    sources = TurnSources(tool_results=[tool])
    assert check_numbers("Has comido 60 g, unas 60 kcal.", sources) == []
    assert len(check_numbers("Son 60125 kcal.", sources)) == 1  # "60.125" is a decimal in JSON


def test_digits_inside_ids_in_tool_results_are_not_origins():
    # An entry id like this one made «3000 kcal» look sourced, now and then (random ids)
    tool = '{"registrado": {"id": "ab3000cd2500ef", "kind": "meal"}, "nutrients": {"kcal": 190.2}}'
    sources = TurnSources(tool_results=[tool])
    assert len(check_numbers("Te quedan 3.000 kcal.", sources)) == 1
    assert check_numbers("Has comido 190 kcal.", sources) == []


# --- review findings (2026-10-12) ---------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "Te quedan 900 de las 2500 de hoy.",  # unitless numbers followed by a word
        "Llevas 1450 calorias.",  # unit without accent
        "Toma 4000 UI de vitamina D.",  # UI
        "Te quedan dos mil kcal.",  # compound number words
        "Son mil quinientas kcal.",
        "Más información [aquí](https://example.org): 300 kcal.",  # a Markdown link is not a citation
        "Toma 3 g/kg [ ].",  # empty citation
        "Toma 1,2–2 g/kg [ISSN 20].",  # partial tag is not a prefix of «ISSN 2017»
        "Te quedan 175 kcal.",  # the profile's height is not the origin of kcal
    ],
)
def test_unsourced_figures_that_used_to_slip_through(answer):
    sources = TurnSources(**{**SOURCES.__dict__, "profile": {"weight_kg": 70, "height_cm": 175, "age": 34}})
    assert len(check_numbers(answer, sources)) >= 1


def test_counts_and_profile_facts_without_unit_are_still_fine():
    sources = TurnSources(profile={"age": 34})
    assert check_numbers("Has hecho 3 comidas y tienes 34 años.", sources) == []


def test_a_citation_with_a_page_is_not_split_into_two_sentences():
    passage = {"EFSA DRV 2017, p. 21": "Water: adequate intake 2.5 L/day for adult men."}
    answer = "La EFSA da 2,5 L al día para hombres adultos [EFSA DRV 2017, p. 21]. Bebe a lo largo del día."
    assert split_sentences(answer)[0].endswith("[EFSA DRV 2017, p. 21].")
    assert check_numbers(answer, TurnSources(tool_results=[], profile={}, user_message="", passages=passage)) == []


def test_a_citation_with_several_places_or_documents_is_expanded():
    from mojo_picon.guardrails.number_origin import citations

    assert citations("Toma 3 mg/kg [ISSN cafeína 2021, §7.2, §10.4].") == [
        "issn cafeína 2021, §7.2",
        "issn cafeína 2021, §10.4",
    ]
    assert citations("Agua [EFSA DRV 2017, p. 21; AESAN 2022].") == ["efsa drv 2017, p. 21", "aesan 2022"]
    assert citations("Proteína [ISSN 2017, §3].") == ["issn 2017, §3"]
    passages = {"ISSN cafeína 2021, §10.4": "Caffeine 3–6 mg/kg improves performance."}
    answer = "Entre 3 y 6 mg/kg mejora el rendimiento [ISSN cafeína 2021, §7.2, §10.4]."
    assert check_numbers(answer, TurnSources(tool_results=[], profile={}, user_message="", passages=passages)) == []


def test_a_per_kg_value_echoed_by_a_tool_still_needs_its_citation():
    # Found by the evaluation (evals/cases/numbers.yaml, num-16): per_kg_target echoes the model's own input
    tool = '{"per_kg_min": 1.6, "per_kg_max": 1.6, "weight_kg": 70, "min": 112, "max": 112, "unit": "g"}'
    sources = TurnSources(tool_results=[tool], profile={"weight_kg": 70}, user_message="", passages={})
    violations = check_numbers("Para tus 70 kg, 1,6 g/kg son 112 g al día.", sources)
    assert [v.quantity.text for v in violations] == ["1,6 g/kg"]  # the 112 g from the tool is fine
    cited = {"ISSN proteína 2017, §0": "1.4–2.0 g protein/kg body weight/day"}
    ok = TurnSources(tool_results=[tool], profile={}, user_message="", passages=cited)
    assert check_numbers("Con 1,4–2 g/kg [ISSN proteína 2017, §0], para ti son 112 g.", ok) == []


def test_the_feedback_tells_the_coach_not_to_apologise_to_the_user():
    # Found by the evaluation (conv-05): after a correction the user read «Tienes toda la razón, disculpa»
    from mojo_picon.guardrails.number_origin import feedback

    violation = check_numbers("Toma 20 g.", TurnSources(tool_results=[], profile={}, user_message="", passages={}))
    assert "sin disculparte" in feedback(violation)


def test_passage_numbers_are_read_as_source_text():
    # Found while checking the expert brief: brackets inside a guideline are data, and English thousands
    from mojo_picon.guardrails.number_origin import passage_numbers

    issn = "15–20% PRO [0.8–1.2 g/kg/day], and 25–35% fat [0.5–1.5 g/kg/day]"
    assert {0.8, 1.2, 0.5, 1.5} <= set(passage_numbers([issn]))
    assert 8000 in passage_numbers(["losses can be up to about 8,000 mL/day"])
    passages = {"ISSN revisión 2018, §1.30": issn}
    answer = "Basta con 0,8–1,2 g/kg de proteína al día [ISSN revisión 2018, §1.30]."
    assert check_numbers(answer, TurnSources(tool_results=[], profile={}, user_message="", passages=passages)) == []
