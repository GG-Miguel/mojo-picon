"""Fast input rules: keywords for clinical signals, extreme goals and obvious jailbreaks.

Cheap and deterministic, before any LLM (Guardrails spec). A rule that says "derivar" is final;
otherwise the LLM classifier also runs and the stricter level wins.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from mojo_picon.tools.foods import normalize

GuardLevel = Literal["ok", "aviso", "derivar"]
SEVERITY = {"ok": 0, "aviso": 1, "derivar": 2}
MAX_SAFE_KG_PER_WEEK = 1.0


class GuardDecision(BaseModel):
    """Structured output of the guardian (also produced by the rules)."""

    level: GuardLevel
    category: str = Field(description="clinical category, jailbreak, off_topic or none")
    reason: str = ""


def stricter(a: GuardDecision, b: GuardDecision) -> GuardDecision:
    return a if SEVERITY[a.level] >= SEVERITY[b.level] else b


# (level, category, pattern) over normalised text (lowercase, no accents).
_RULES: list[tuple[GuardLevel, str, re.Pattern[str]]] = [
    (
        "derivar",
        "jailbreak",
        re.compile(
            r"\b(ignora|olvida|salta(te)?)\b.{0,20}\b(instrucciones|reglas|normas|restricciones)\b"
            r"|sin (ninguna )?restricci|modo desarrollador|prompt del sistema|system prompt"
        ),
    ),
    (
        "derivar",
        "medication",
        re.compile(
            r"\b(insulina|medicacion|medicamentos?|pastillas?|farmacos?|metformina|antibioticos?|anticoagulantes?)\b"
        ),
    ),
    (
        "derivar",
        "eating_disorder",
        re.compile(
            r"\b(vomitar|vomito|purgar(me)?|purgas?|laxantes|atracon(es)?|anorexia|bulimia|me doy asco"
            r"|dejar de comer|no comer nada|saltarme todas las comidas)\b"
        ),
    ),
    ("derivar", "diabetes", re.compile(r"\bdiabet")),
    ("derivar", "kidney_disease", re.compile(r"\b(enfermedad renal|insuficiencia renal|dialisis)\b")),
    ("derivar", "fever", re.compile(r"\bfiebre\b")),
    ("derivar", "minor", re.compile(r"\btengo ([1-9]|1[0-7]) anos\b")),
    ("derivar", "diagnosis", re.compile(r"\b(que enfermedad tengo|diagnostic|tengo cancer|tengo un tumor)\b")),
]
_PREGNANCY = re.compile(r"\b(embarazada|embarazo|gestacion|lactancia|dando el pecho)\b")
_PREGNANCY_CLINICAL = re.compile(r"\b(adelgazar|perder peso|bajar de peso|kcal|calorias|dieta|deficit|suplement)")
_COLD = re.compile(r"\b(resfriad[oa]|catarro|constipad[oa]|gripe|dolor de garganta)\b")
_COUNT = r"(\d+(?:[.,]\d+)?|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince)"
_WEIGHT_GOAL = re.compile(
    r"\b(perder|bajar|adelgazar|quitarme)\b\D{0,15}(\d+(?:[.,]\d+)?)\s*(kg|kilos?)\b\D{0,20}"
    rf"\b(en|para)\s+{_COUNT}\s+(dias?|semanas?|mes|meses)(\s+y\s+medio)?\b"
)
_THIS_WEEK = re.compile(
    r"\b(perder|bajar|adelgazar|quitarme)\b\D{0,15}(\d+(?:[.,]\d+)?)\s*(kg|kilos?)\b\D{0,15}"
    r"\b(esta|en esta|la proxima|en una|para esta) semana\b"
)
_UNITS = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "quince": 15,
}  # fmt: skip
_WEEKS_PER = {"dia": 1 / 7, "semana": 1, "mes": 4.3}


def classify_by_rules(text: str) -> GuardDecision:
    norm = normalize(text)
    decision = GuardDecision(level="ok", category="none")
    for level, category, pattern in _RULES:
        if pattern.search(norm):
            decision = stricter(decision, GuardDecision(level=level, category=category, reason="rule"))
    if _PREGNANCY.search(norm):
        clinical = _PREGNANCY_CLINICAL.search(norm)
        candidate = GuardDecision(
            level="derivar" if clinical else "aviso",
            category="pregnancy_clinical" if clinical else "pregnancy",
            reason="rule",
        )
        decision = stricter(decision, candidate)
    if _COLD.search(norm):
        decision = stricter(decision, GuardDecision(level="aviso", category="mild_illness", reason="rule"))
    this_week = _THIS_WEEK.search(norm)
    if this_week and float(this_week.group(2).replace(",", ".")) > MAX_SAFE_KG_PER_WEEK:
        decision = stricter(decision, GuardDecision(level="derivar", category="extreme_goal", reason="rule"))
    if (goal := _WEIGHT_GOAL.search(norm)) and _kg_per_week(goal) > MAX_SAFE_KG_PER_WEEK:
        decision = stricter(decision, GuardDecision(level="derivar", category="extreme_goal", reason="rule"))
    return decision


def _kg_per_week(match: re.Match[str]) -> float:
    kg = float(match.group(2).replace(",", "."))
    count = match.group(5)
    n = _UNITS[count] if count in _UNITS else float(count.replace(",", "."))
    if match.group(7):  # «un mes y medio»
        n += 0.5
    unit = next(u for u in _WEEKS_PER if match.group(6).startswith(u))  # días, semanas, mes(es)
    weeks = n * _WEEKS_PER[unit]
    return kg / weeks if weeks else float("inf")
