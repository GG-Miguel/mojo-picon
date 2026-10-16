"""BM25 sparse vectors computed here; Qdrant adds the IDF (Modifier.IDF) and fuses with the dense
search (RRF). Pure Python: no extra model to download, deterministic and testable.

Document weight of a term: tf·(k1+1) / (tf + k1·(1 − b + b·len/avg_len)). Query: weight 1 per term.
Terms are lower-cased, without accents and hashed to 31-bit indices; Spanish and English stop
words are dropped (the corpus has both languages).
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from collections import Counter

K1 = 1.2
B = 0.75
AVG_LEN = 250.0  # average chunk length in terms; only scales document length normalisation

STOP_WORDS = frozenset(
    [
    # Spanish
    "a", "al", "algo", "como", "con", "de", "del", "el", "en", "es", "esta", "este", "esto", "la", "las",
    "lo", "los", "mas", "o", "para", "pero", "por", "que", "se", "sin", "su", "sus", "un", "una", "uno", "y",
    "ya",
    # English
    "the", "of", "and", "to", "in", "is", "are", "be", "for", "on", "with", "as", "by", "or", "an", "at",
    "that", "this", "it", "from", "was", "were", "which", "their", "its", "can", "may", "not", "has", "have",
    "been", "also", "than", "these", "those", "such", "into", "per",
    ]
)  # fmt: skip
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")


def tokenize(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [t for t in _TOKEN_RE.findall(plain) if t not in STOP_WORDS and len(t) > 1]


def _index(term: str) -> int:
    return zlib.crc32(term.encode()) & 0x7FFFFFFF


def document_vector(text: str) -> tuple[list[int], list[float]]:
    terms = tokenize(text)
    counts = Counter(_index(t) for t in terms)
    norm = K1 * (1 - B + B * len(terms) / AVG_LEN)
    indices = sorted(counts)
    return indices, [counts[i] * (K1 + 1) / (counts[i] + norm) for i in indices]


def query_vector(text: str) -> tuple[list[int], list[float]]:
    indices = sorted({_index(t) for t in tokenize(text)})
    return indices, [1.0] * len(indices)
