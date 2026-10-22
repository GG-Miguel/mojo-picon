"""Allergens of a package's ingredients list, found by keyword: the code's own check of the vision model.

The model reads the list and names the allergens it declares; this module reads the same list again
with the Spanish names of the 14 allergens of EU Regulation 1169/2011 (Annex II), and the union of
both is what counts. A false alarm (nutmeg is not a tree nut) costs a question; a missed allergen can
cost much more, so the words err on the side of warning.
"""

from __future__ import annotations

import re
import unicodedata

from mojo_picon.domain.food import Allergen

WORDS: dict[Allergen, tuple[str, ...]] = {
    Allergen.GLUTEN: ("gluten", "trigo", "cebada", "centeno", "avena", "espelta", "kamut", "seitan"),
    Allergen.CRUSTACEANS: ("crustaceo", "gamba", "langostino", "cangrejo", "bogavante", "cigala", "camaron"),
    Allergen.EGGS: ("huevo", "yema", "ovoalbumina", "ovoproducto"),
    Allergen.FISH: ("pescado", "anchoa", "atun", "bacalao", "salmon", "merluza", "sardina", "surimi"),
    Allergen.PEANUTS: ("cacahuete", "mani"),
    Allergen.SOY: ("soja", "soya"),
    Allergen.MILK: (
        "leche",
        "lactosa",
        "lacteo",
        "suero lacteo",
        "nata",
        "mantequilla",
        "queso",
        "caseina",
        "caseinato",
        "lactosuero",
        "yogur",
    ),
    Allergen.TREE_NUTS: (
        "frutos de cascara",
        "almendra",
        "avellana",
        "nuez",
        "nueces",
        "anacardo",
        "pistacho",
        "pacana",
        "macadamia",
    ),
    Allergen.CELERY: ("apio",),
    Allergen.MUSTARD: ("mostaza",),
    Allergen.SESAME: ("sesamo", "ajonjoli", "tahin", "tahini"),
    Allergen.SULPHITES: (
        "sulfito",
        "disulfito",
        "bisulfito",
        "metabisulfito",
        "anhidrido sulfuroso",
        "dioxido de azufre",
        r"e-?22[0-8]",
    ),
    Allergen.LUPIN: ("altramuz", "altramuces", "lupino"),
    Allergen.MOLLUSCS: ("molusco", "mejillon", "almeja", "berberecho", "calamar", "pulpo", "sepia", "ostra"),
}
# A word and its plural (s / es), at word boundaries, on text without accents or case
_PATTERNS = {a: re.compile(r"\b(" + "|".join(words) + r")(e?s)?\b") for a, words in WORDS.items()}
_MAY_CONTAIN = re.compile(r"\bpuede contener\b|\btrazas\b")


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def find(text: str) -> frozenset[Allergen]:
    """The allergens named in a text."""
    text = plain(text)
    return frozenset(a for a, pattern in _PATTERNS.items() if pattern.search(text))


def in_ingredients(ingredients: list[str]) -> tuple[frozenset[Allergen], frozenset[Allergen]]:
    """(contains, may contain) from an ingredients list; a «puede contener» or «trazas» entry is a trace."""
    contains: set[Allergen] = set()
    traces: set[Allergen] = set()
    for ingredient in ingredients:
        (traces if _MAY_CONTAIN.search(plain(ingredient)) else contains).update(find(ingredient))
    return frozenset(contains), frozenset(traces - contains)
