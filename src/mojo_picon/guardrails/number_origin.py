"""Number-origin check for the output guardrail (ADR-19, revised 2026-10-12).

Every number in the Coach's answer must have the origin that matches its kind:
- PERSONAL  (kcal, g, mg for this user, no citation): tool results, profile or user message.
- REFERENCE (g/kg, ml, %, or any nutrient figure in a cited sentence): a passage cited
  in the same sentence (expert brief or RAG chunk), or a tool result.
- IGNORED   (times, dates, distances, counts): not checked.
Numbers the user wrote are always accepted.

Pure code: no LLM, no I/O. The output node (guardrails/output.py) builds the
TurnSources, calls check_numbers() and decides whether to regenerate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from mojo_picon.tools.foods import normalize


class Kind(StrEnum):
    PERSONAL = "personal"
    REFERENCE = "reference"
    IGNORED = "ignored"


@dataclass(frozen=True)
class Quantity:
    low: float
    high: float  # == low for a single value
    unit: str | None
    text: str  # as written, e.g. "1,2–2 g/kg"
    sentence: int  # index in split_sentences()
    next_word: str | None = None  # first word after the number, if it is not a unit


@dataclass(frozen=True)
class Violation:
    quantity: Quantity
    kind: Kind
    reason: str


@dataclass
class TurnSources:
    """Everything a number may legitimately come from in this turn."""

    tool_results: list[object] = field(default_factory=list)  # raw tool outputs (dicts, lists, numbers)
    profile: Mapping[str, object] = field(default_factory=dict)
    user_message: str = ""  # original text, before Presidio
    passages: Mapping[str, str] = field(default_factory=dict)  # citation tag -> passage text (brief + RAG of the turn)


# --- Extraction --------------------------------------------------------------

# Longest units first so "g/kg" wins over "g".
_UNITS = {
    "kcal": "kcal",
    "kcals": "kcal",
    "kilocalorías": "kcal",
    "kilocalorias": "kcal",
    "calorías": "kcal",
    "calorias": "kcal",
    "kj": "kj",
    "kilojulios": "kj",
    "ui": "ui",
    "µg": "µg",
    "mcg": "µg",
    "microgramos": "µg",
    "g/kg": "g/kg",
    "gramos por kilo": "g/kg",
    "g por kg": "g/kg",
    "mg": "mg",
    "miligramos": "mg",
    "g": "g",
    "gr": "g",
    "gramos": "g",
    "gramo": "g",
    "kg": "kg",
    "kilos": "kg",
    "kilogramos": "kg",
    "ml": "ml",
    "mililitros": "ml",
    "l": "l",
    "litros": "l",
    "litro": "l",
    "%": "%",
    "por ciento": "%",
    "km": "km",
    "kilómetros": "km",
    "kilometros": "km",
    "min": "min",
    "minutos": "min",
    "h": "h",
    "horas": "h",
    "hora": "h",
}
_UNIT_RE = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))

# Spanish format: "1.400" (thousands), "1,2" (decimal). A dot followed by exactly
# three digits is a thousands separator; any other dot is a decimal point.
_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"
_QUANTITY_RE = re.compile(
    rf"(?:entre\s+)?(?P<a>{_NUM})"
    rf"(?:\s*(?:–|-|a|y)\s*(?P<b>{_NUM}))?"
    rf"(?:\s*(?P<unit>{_UNIT_RE})(?![\w/]))?"
    rf"(?=\s+(?P<word>[^\W\d_]+))?",  # lookahead: the word is not part of the match
    re.IGNORECASE,
)

_FRACTIONS = {"medio": 0.5, "media": 0.5, "un cuarto": 0.25}
_WORD_NUMBERS = {
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "quince": 15,
    "veinte": 20,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "doscientas": 200,
    "trescientos": 300,
    "trescientas": 300,
    "cuatrocientos": 400,
    "cuatrocientas": 400,
    "quinientos": 500,
    "quinientas": 500,
    "seiscientos": 600,
    "seiscientas": 600,
    "setecientos": 700,
    "setecientas": 700,
    "ochocientos": 800,
    "ochocientas": 800,
    "novecientos": 900,
    "novecientas": 900,
    "mil": 1000,
}
_WORD = "|".join(sorted(map(re.escape, _WORD_NUMBERS), key=len, reverse=True))
_WORD_NUM_RE = re.compile(
    rf"\b(?P<w>{'|'.join(map(re.escape, _FRACTIONS))}|(?:{_WORD})(?:\s+(?:y\s+)?(?:{_WORD}))*)"
    rf"\s+(?P<unit>{_UNIT_RE})(?![\w/])",
    re.IGNORECASE,
)

# Removed before extraction: Markdown links, citation tags ("[ISSN 2017, §3]"), times and dates.
_LINK_RE = re.compile(r"\[[^\[\]]*\]\([^)]*\)")
_CITATION_RE = re.compile(r"\[([^\[\]]+)\](?!\()")
MIN_TAG_CHARS = 3
_STRIP_RE = re.compile(
    r"\[[^\[\]]*\](?:\([^)]*\))?"  # citation tags and Markdown links
    r"|\b\d{1,2}:\d{2}\b"  # 18:30
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"  # 12/10, 12/10/2026
    r"|\b\d{4}-\d{2}-\d{2}\b"  # 2026-10-12
    r"|\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)


def parse_number(text: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", text):
        text = text.replace(".", "")
    return float(text.replace(",", "."))


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", text, flags=re.MULTILINE)  # list markers ("1. ", "- ")
    # Split on . ! ? or newlines, but not on decimal points ("1.5") or thousands ("1.400").
    parts = re.split(r"(?<=[.!?])(?!\d)\s+|\n+", text)
    return [p for p in (s.strip() for s in parts) if p]


def citations(sentence: str) -> list[str]:
    """Citation tags of a sentence (not Markdown links; too short tags are ignored)."""
    tags = (_normalize_tag(t) for t in _CITATION_RE.findall(_LINK_RE.sub(" ", sentence)))
    return [t for t in tags if len(t) >= MIN_TAG_CHARS]


def _parse_words(words: str) -> float:
    """Spanish number words: «dos mil» = 2000, «mil quinientas» = 1500, «medio» = 0.5."""
    key = words.lower()
    if key in _FRACTIONS:
        return _FRACTIONS[key]
    total = current = 0.0
    for word in key.split():
        if word == "y":
            continue
        if word == "mil":
            total += max(current, 1) * 1000
            current = 0
        else:
            current += _WORD_NUMBERS[word]
    return total + current


def extract_quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    for i, sentence in enumerate(split_sentences(text)):
        clean = _STRIP_RE.sub(" ", sentence)
        for m in _WORD_NUM_RE.finditer(clean):
            value = _parse_words(m["w"])
            out.append(Quantity(value, value, _UNITS[m["unit"].lower()], m.group(0), i))
        for m in _QUANTITY_RE.finditer(clean):
            low = parse_number(m["a"])
            high = parse_number(m["b"]) if m["b"] else low
            unit = _UNITS[m["unit"].lower()] if m["unit"] else None
            word = m["word"].lower() if m["word"] else None
            out.append(Quantity(min(low, high), max(low, high), unit, m.group(0).strip(), i, word))
    return out


# --- Classification ----------------------------------------------------------

_PERSONAL_UNITS = {"kcal", "kj", "g", "mg", "µg", "ui"}
# Unitless numbers followed by one of these are counts, not amounts («3 comidas», «2 tostadas»).
_COUNT_NOUNS = {
    "comida",
    "toma",
    "racion",
    "pieza",
    "tostada",
    "rebanada",
    "huevo",
    "vaso",
    "taza",
    "plato",
    "vez",
    "veces",
    "dia",
    "semana",
    "mes",
    "ano",
    "serie",
    "repeticion",
    "unidad",
    "cucharada",
    "fruta",
    "porcion",
    "galleta",
    "yogur",
    "yogures",
    "paso",
    "litro",
    "punto",
    "opcion",
    "idea",
}
_REFERENCE_UNITS = {"g/kg", "ml", "l", "%"}
_IGNORED_UNITS = {"km", "min", "h", "kg"}  # kg: body weight comes from the profile, but is not a nutrition figure


def classify(q: Quantity, cited: bool) -> Kind:
    if q.unit in _IGNORED_UNITS:
        return Kind.IGNORED
    if q.unit in _REFERENCE_UNITS:
        return Kind.REFERENCE
    if q.unit in _PERSONAL_UNITS:
        return Kind.REFERENCE if cited else Kind.PERSONAL
    # No unit: «3 comidas», «2 tostadas» are counts. Any other unitless number («te quedan 900 de
    # las 2500») is treated as personal (when in doubt, the strictest rule).
    if q.next_word is not None and _is_count_noun(q.next_word):
        return Kind.IGNORED
    return Kind.REFERENCE if cited else Kind.PERSONAL


def _is_count_noun(word: str) -> bool:
    w = normalize(word)
    return w in _COUNT_NOUNS or w.removesuffix("s") in _COUNT_NOUNS or w.removesuffix("es") in _COUNT_NOUNS


# --- Matching ----------------------------------------------------------------


def _close(a: float, b: float) -> bool:
    # Rounding tolerance. From 10 up: ±1 unit or ±2 %, whichever is larger ("618" vs "620" passes).
    # Below 10 (g/kg, litres): ±5 %, so "1,5" does not pass for "1,6".
    if abs(b) >= 10:
        return abs(a - b) <= max(1.0, 0.02 * abs(b))
    return abs(a - b) <= 0.05 * max(abs(b), 1) + 1e-9


def numbers_in(obj: object) -> list[float]:
    """All numeric values inside a tool result, profile or text (recursively)."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped[:1] in ("{", "["):
            # Tool results are JSON: read the numbers as JSON numbers ("60.125" is not 60125)
            try:
                return _json_numbers(json.loads(stripped))
            except ValueError:
                pass
        return [v for q in extract_quantities(obj) for v in (q.low, q.high)] + [
            parse_number(n) for n in re.findall(_NUM, _CITATION_RE.sub(" ", obj))
        ]
    if isinstance(obj, Mapping):
        return [v for x in obj.values() for v in numbers_in(x)]
    if isinstance(obj, Iterable):
        return [v for x in obj for v in numbers_in(x)]
    return []


def _json_numbers(obj: object) -> list[float]:
    """Numeric values of parsed JSON. Strings inside it are ignored: ids like "edcbc04c3000…" or
    food names are not the origin of any figure."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, Mapping):
        return [v for x in obj.values() for v in _json_numbers(x)]
    if isinstance(obj, list):
        return [v for x in obj for v in _json_numbers(x)]
    return []


def _matches(q: Quantity, pool: list[float]) -> bool:
    return all(any(_close(v, p) for p in pool) for v in {q.low, q.high})


def _normalize_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", tag).strip().lower()


def _cited_passages(tags: list[str], passages: Mapping[str, str]) -> list[str]:
    # A citation matches its passage, or the passages of its sections: "[ISSN 2017]" -> "ISSN 2017, §3"
    # (prefix up to a word boundary, so "[issn 20]" does not match "issn 2017").
    norm = {_normalize_tag(k): v for k, v in passages.items()}
    return [
        text
        for tag in tags
        for key, text in norm.items()
        if key == tag or key.startswith(tag + ",") or key.startswith(tag + " ")
    ]


def check_numbers(answer: str, sources: TurnSources) -> list[Violation]:
    sentences = split_sentences(answer)
    user_pool = numbers_in(sources.user_message)
    tool_pool = numbers_in(sources.tool_results)
    profile_pool = numbers_in(sources.profile)  # age, height…: only for unitless numbers («tus 34 años»)

    violations: list[Violation] = []
    for q in extract_quantities(answer):
        # Only tags that resolve to a known passage count as a citation (no "[ ]" or made-up tags)
        tags = [t for t in citations(sentences[q.sentence]) if _cited_passages([t], sources.passages)]
        kind = classify(q, cited=bool(tags))
        if kind is Kind.IGNORED or _matches(q, user_pool):
            continue
        if kind is Kind.PERSONAL:
            pool = tool_pool + (profile_pool if q.unit is None else [])
            if not _matches(q, pool):
                violations.append(
                    Violation(q, kind, f"«{q.text}» no sale de ninguna herramienta del turno ni del perfil")
                )
        else:
            reference_pool = numbers_in(_cited_passages(tags, sources.passages)) + tool_pool
            if not tags:
                if not _matches(q, reference_pool):
                    violations.append(Violation(q, kind, f"«{q.text}» es un valor de referencia sin cita"))
            elif not _matches(q, reference_pool):
                violations.append(Violation(q, kind, f"«{q.text}» no aparece en la fuente citada ({', '.join(tags)})"))
    return violations


def feedback(violations: list[Violation]) -> str:
    """Message for the single regeneration attempt."""
    lines = "\n".join(f"- {v.reason}" for v in violations)
    return (
        "Tu respuesta contiene cifras sin origen verificable:\n"
        f"{lines}\n"
        "Usa solo cifras de las herramientas de este turno, del perfil o del mensaje del usuario. "
        "Los valores de referencia deben llevar la etiqueta de su fuente en la misma frase. "
        "Si necesitas una cantidad personal por kg de peso, llama a per_kg_target."
    )


def drop_sentences(answer: str, violations: list[Violation]) -> str:
    """Fallback after a failed regeneration: remove whole sentences with unsourced numbers."""
    bad = {v.quantity.sentence for v in violations}
    kept = [s for i, s in enumerate(split_sentences(answer)) if i not in bad]
    return " ".join([*kept, "No tengo un dato fiable para darte alguna de las cifras que me pedías."])


def index_brief(markdown: str) -> dict[str, str]:
    """Expert brief index: citation tag -> text of every line that carries it."""
    index: dict[str, list[str]] = {}
    for line in markdown.splitlines():
        for tag in _CITATION_RE.findall(line):
            index.setdefault(tag.strip(), []).append(line)
    return {tag: "\n".join(lines) for tag, lines in index.items()}
