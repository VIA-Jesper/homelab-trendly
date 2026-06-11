"""
dedup.py - Canonical keys for article/product de-duplication.

WHY THIS EXISTS
  De-dup logic used to live in two places that disagreed:
    - scripts/suggest_articles.is_known()  - exact PR id OR exact lowercased name
    - api/routes/jobs.py duplicate check    - positional, exact name, same-type only
  Both were brittle (missed harmless name variants) and the API check was buggy:
  it compared products only at identical array positions, and only within the
  same article_type, so a single review and a roundup containing the same
  product never collided.

  This module is the single source of truth for the two canonical keys, imported
  by both the API and the planner scripts so they always agree:

    canonical_product_key(name, pid, url) - identifies a *product* across listings.
    slot_key(article_type, category, product_keys) - identifies an *article slot*
        (its subject + format), i.e. the unit the coverage ledger tracks.

  Pure functions, stdlib only - trivially unit-testable, no DB, no network, no
  third-party deps.

SEGMENTS (Phase 1)
  slot_key() currently derives a roundup's identity from its product set. The
  segment-aware planner (Phase 1) will pass an explicit `segment` so that
  "bedste robotstøvsuger til kæledyr" and "...til små lejligheder" are distinct
  slots even when their product sets overlap. Until then, roundups are keyed by
  product set.
"""

import re
import unicodedata

_WS = re.compile(r"\s+")
# Keep digits, ASCII letters, and Nordic letters; everything else becomes a space.
_NON_KEY = re.compile(r"[^0-9a-zæøåäöü ]")
_DIGITS = re.compile(r"\d+")


def normalize_text(value: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Keeps Nordic letters."""
    if not value:
        return ""
    s = unicodedata.normalize("NFC", value).lower()
    s = _NON_KEY.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _name_token_key(name: str) -> str:
    """
    Order-independent token key for a product name. 'Roborock S8 Pro Ultra' and
    'Ultra Pro S8 Roborock' collapse to the same key, so harmless word reordering
    or duplicated brand tokens between PriceRunner snapshots don't read as a new
    product.
    """
    tokens = sorted(set(normalize_text(name).split()))
    return " ".join(tokens)


def _pr_id(pid: str | None, url: str | None) -> str | None:
    """
    Extract a bare PriceRunner numeric id from a product URL ('.../pl/19-3206825946/...')
    or an id field ('pr_3206825946' or '3206825946'). URL wins when both are present.
    """
    if url:
        m = re.search(r"/pl/\d+-(\d+)", url)
        if m:
            return m.group(1)
    if pid:
        m = _DIGITS.search(str(pid))
        if m:
            return m.group(0)
    return None


def canonical_product_key(name: str = "", pid: str | None = None, url: str | None = None) -> str:
    """
    Stable identity for a product. Prefers the PriceRunner numeric id (robust
    across name changes); falls back to an order-independent name token key.

    Returns e.g. 'pr:3206825946' or 'nm:pro roborock s8 ultra'. Returns 'nm:' for
    a product with neither an id nor a name (caller should treat as non-matchable).
    """
    bare = _pr_id(pid, url)
    if bare:
        return f"pr:{bare}"
    return f"nm:{_name_token_key(name)}"


def normalize_category(category: str) -> str:
    """
    Canonical category key. brief.category is already a mapped slug; this only
    makes matching robust to case / whitespace / punctuation drift.
    """
    return normalize_text(category).replace(" ", "-")


def slot_key(
    article_type: str,
    category: str,
    product_keys: list[str],
    segment: str | None = None,
) -> str:
    """
    Canonical identity of an *article slot* - the unit the coverage ledger tracks.
    Two jobs with the same slot_key are the same article and must not coexist.

      single-product-review : <cat>:single:<product>
      comparison            : <cat>:comparison:<sorted product set>
      hero / roundup        : <cat>:roundup:<segment | sorted product set>

    `product_keys` should be canonical_product_key() values. The planner (Phase 1)
    passes `segment` for roundups; until then roundups are identified by product set.
    """
    cat = normalize_category(category)
    keys = sorted(set(product_keys))
    if article_type == "single-product-review":
        return f"{cat}:single:{keys[0] if keys else ''}"
    if article_type == "comparison":
        return f"{cat}:comparison:{'|'.join(keys)}"
    # hero / roundup and any future multi-product format
    if segment:
        return f"{cat}:roundup:{normalize_text(segment).replace(' ', '-')}"
    return f"{cat}:roundup:{'|'.join(keys)}"
