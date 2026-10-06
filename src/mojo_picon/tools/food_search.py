"""Food tools: search_food, get_nutrients and check_allergens over the curated table.

search_food never invents a food: it returns candidates with a confidence and a status, and
the agent asks the user when the result is ambiguous («¿arroz blanco o integral?»)
(specs/food-table.md, "How search_food searches").
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from mojo_picon.domain import Allergen, Food, Nutrients
from mojo_picon.tools.foods import normalize

MAX_CANDIDATES = 5
CONFIDENCE_EXACT = 1.0
CONFIDENCE_CONTAINS = 0.7
TYPO_PENALTY = 0.9  # a query fixed for typos is never an exact match
UNKNOWN_WORDS_PENALTY = 0.9  # same when words not in the table are ignored («un plato de arroz»)
STOPWORDS = {"de", "del", "la", "el", "los", "las", "con", "y", "a", "al", "en", "un", "una", "unos", "unas"}


class SearchStatus(StrEnum):
    EXACT = "exact"  # one food, exact name or synonym: can be used directly
    APPROXIMATE = "approximate"  # one candidate, not exact (partial or typo): confirm with the user
    AMBIGUOUS = "ambiguous"  # several candidates: ask the user which one
    NOT_FOUND = "not_found"  # nothing: ask the user or use the barcode; never invent nutrients


@dataclass(frozen=True)
class Candidate:
    food_id: str
    name: str
    confidence: float
    matched: str  # the name or synonym that matched


@dataclass(frozen=True)
class SearchResult:
    query: str
    status: SearchStatus
    candidates: list[Candidate]


class UnknownFoodError(KeyError):
    """The food id is not in the table."""


class FoodIndex:
    """Search index over the food table, built once at start-up."""

    def __init__(self, foods: Mapping[str, Food]):
        self.foods = dict(foods)
        terms: list[tuple[str, Food, bool]] = []  # (term, food, is_name)
        for food in self.foods.values():
            terms.append((food.name, food, True))
            terms.extend((s, food, False) for s in food.synonyms)

        self._vocabulary = {w for term, _, _ in terms for w in _words(term)}
        self._canonical = _singular_plural_map(self._vocabulary)
        self._exact: dict[str, tuple[Food, str]] = {}
        self._name_tokens: list[tuple[frozenset[str], Food, str]] = []
        for term, food, is_name in terms:
            key = self._key(term)
            self._exact.setdefault(key, (food, term))
            if is_name:
                self._name_tokens.append((frozenset(key.split()) - STOPWORDS, food, term))

    def search(self, query: str) -> SearchResult:
        key = self._key(query)
        if not key:
            return SearchResult(query, SearchStatus.NOT_FOUND, [])
        candidates = self._candidates(key, penalty=1.0)
        if not candidates:
            corrected = " ".join(self._near(w) or w for w in key.split())
            if corrected != key:
                candidates = self._candidates(corrected, penalty=TYPO_PENALTY)
        if not candidates:
            # Drop words that are neither in the table nor a typo of a table word («plato», «vaso»,
            # «dos»). A typo like «arros» is kept, so «arros con pollo» is not reduced to «pollo».
            known = _strip_stopwords(" ".join(w for w in key.split() if w in self._vocabulary or self._near(w)))
            if known and known != key:
                candidates = self._candidates(known, penalty=UNKNOWN_WORDS_PENALTY)
        candidates = sorted(candidates, key=lambda c: (-c.confidence, len(c.name)))[:MAX_CANDIDATES]
        return SearchResult(query, _status(candidates), candidates)

    def _candidates(self, key: str, penalty: float) -> list[Candidate]:
        found: dict[str, Candidate] = {}
        exact = self._exact.get(key)
        if exact:
            food, term = exact
            found[food.id] = Candidate(food.id, food.name, round(CONFIDENCE_EXACT * penalty, 2), term)
        tokens = frozenset(key.split()) - STOPWORDS
        if tokens:
            for name_tokens, food, term in self._name_tokens:
                if food.id in found or not tokens <= name_tokens:
                    continue
                # With an exact match, only foods of the same category are alternatives
                # («arroz» -> other rices, not «salsa de tomate» for «tomate»).
                if exact and food.category != exact[0].category:
                    continue
                found[food.id] = Candidate(food.id, food.name, round(CONFIDENCE_CONTAINS * penalty, 2), term)
        return list(found.values())

    def _key(self, text: str) -> str:
        return _strip_stopwords(" ".join(self._canonical.get(w, w) for w in _words(text)))

    def _near(self, word: str) -> str | None:
        """The table word this one is a typo of, if any: 1 edit for 4-7 letters, 2 for longer."""
        if word in self._vocabulary or word in STOPWORDS or len(word) < 4:
            return None
        limit = 1 if len(word) < 8 else 2
        best = min(
            ((_edit_distance(word, v), v) for v in self._vocabulary if abs(len(v) - len(word)) <= limit),
            default=None,
        )
        if best is None or best[0] > limit:
            return None
        return self._canonical.get(best[1], best[1])


def get_nutrients(foods: Mapping[str, Food], food_id: str, grams: float = 100) -> Nutrients:
    """Nutrients of `grams` of a food, from the table. Raises UnknownFoodError if it does not exist."""
    if grams <= 0:
        raise ValueError("grams must be positive")
    food = foods.get(food_id)
    if food is None:
        raise UnknownFoodError(food_id)
    return food.nutrients_for(grams)


def check_allergens(
    foods: Mapping[str, Food], food_ids: Iterable[str], allergens: frozenset[Allergen]
) -> dict[str, frozenset[Allergen]]:
    """For each food that contains any of `allergens`, which ones. Unknown ids raise UnknownFoodError."""
    result = {}
    for food_id in food_ids:
        food = foods.get(food_id)
        if food is None:
            raise UnknownFoodError(food_id)
        found = food.allergens & allergens
        if found:
            result[food_id] = found
    return result


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9ñ]+", normalize(text).replace("%", " "))


def _singular_plural_map(vocabulary: set[str]) -> dict[str, str]:
    """Map singular and plural forms to the word used in the table («tomates» -> «tomate»,
    «nuez» -> «nueces», «pechugas» -> «pechuga»). Words of the table map to themselves."""
    canonical = {w: w for w in vocabulary}
    for w in sorted(vocabulary):
        forms = {w + "s", w + "es"}
        if w.endswith("z"):
            forms.add(w[:-1] + "ces")
        if w.endswith("ces"):
            forms.add(w[:-3] + "z")
        if w.endswith("es"):
            forms.add(w[:-2])
        if w.endswith("s"):
            forms.add(w[:-1])
        for form in forms:
            canonical.setdefault(form, w)
    return canonical


def _strip_stopwords(key: str) -> str:
    """Remove stopwords at both ends («un plato de arroz» -> «plato de arroz»), keep inner ones."""
    words = key.split()
    while words and words[0] in STOPWORDS:
        words.pop(0)
    while words and words[-1] in STOPWORDS:
        words.pop()
    return " ".join(words)


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance with transpositions (optimal string alignment)."""
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            value = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                value = min(value, prev2[j - 2] + 1)
            cur.append(value)
        prev2, prev = prev, cur
    return prev[-1]


def _status(candidates: list[Candidate]) -> SearchStatus:
    if not candidates:
        return SearchStatus.NOT_FOUND
    if len(candidates) > 1:
        return SearchStatus.AMBIGUOUS
    if candidates[0].confidence >= CONFIDENCE_EXACT:
        return SearchStatus.EXACT
    return SearchStatus.APPROXIMATE
