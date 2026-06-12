"""
similarity.py - lexical near-duplicate detection for the uniqueness gate (Phase 2B).

WHY
  The slot system stops duplicate *topics*, but at scale two articles on different
  products can still read near-identically (same template, swapped names). Google's
  scaled-content-abuse policy demotes exactly that sameness. This module measures
  how much an article's prose overlaps an existing one, so QA can block a near-dup.

HOW
  Word n-gram (shingle) Jaccard similarity. Two genuinely different articles share
  vocabulary but few exact 5-word runs; a templated near-dup shares many. MinHash /
  embeddings (Phase 3) only matter when the corpus is large - exact Jaccard is fine
  at homelab scale.

PURE / STDLIB-ONLY - no config/DB, unit-testable in isolation (like services.dedup).
"""

import re

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")   # [text](url) -> text
_NON_WORD = re.compile(r"[^0-9a-zæøåäöü ]+")

DEFAULT_K = 5


def normalize(text: str) -> str:
    """Lowercase, unwrap markdown links to their text, drop punctuation, collapse space.
    Keeps Nordic letters so Danish prose compares correctly."""
    text = _MD_LINK.sub(r"\1", text or "")
    text = _NON_WORD.sub(" ", text.lower())
    return " ".join(text.split())


def shingles(text: str, k: int = DEFAULT_K) -> set[str]:
    """Set of k-word shingles. Short texts (< k words) collapse to a single shingle."""
    words = normalize(text).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def similarity(text_a: str, text_b: str, k: int = DEFAULT_K) -> float:
    """Shingle Jaccard similarity of two texts, 0.0 - 1.0."""
    return jaccard(shingles(text_a, k), shingles(text_b, k))


def max_similarity(text: str, corpus: list[str], k: int = DEFAULT_K) -> tuple[float, int]:
    """Highest similarity of `text` against any item in corpus.
    Returns (score, index); (0.0, -1) if corpus is empty. The shingles of `text`
    are computed once and reused across the corpus."""
    s = shingles(text, k)
    if not s:
        return 0.0, -1
    best, idx = 0.0, -1
    for i, other in enumerate(corpus):
        score = jaccard(s, shingles(other, k))
        if score > best:
            best, idx = score, i
    return best, idx
