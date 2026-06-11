"""
value_signals.py - pre-computed comparative facts for a brief's product set (Phase 2A).

WHY THIS EXISTS
  Google's March/May 2026 core updates demote affiliate content that just restates
  manufacturer specs with no first-hand or unique value. The cheapest, most
  deterministic "unique value" we can add is COMPARATIVE analysis across the
  products we already fetched: which is cheapest, which leads on a given spec,
  which has a feature the others lack. The LLM cannot fabricate these (they depend
  on the live set) and no manufacturer page carries them - so they are exactly the
  kind of original analysis that earns the right to rank.

COMPLIANCE
  These are facts WE derive from the brief's own products (price, specs), not
  PriceRunner platform data. They are fully citable in the article body. This is
  the opposite of watcher/rank/shop-count signals (see generate_base.txt), which
  must never be quoted by number.

PURE / STDLIB-ONLY
  No config, DB, or pydantic imports - takes plain dicts so it is unit-testable in
  isolation (like services.dedup) and reusable by the brief builder and scripts.
"""

import re
import statistics

# Spec keys that are platform/meta signals, not product features. Never compared
# or surfaced as "value" (the prompt forbids quoting them, and brand is identity,
# not a feature you win or lose on).
_EXCLUDE_SPEC_KEYS = {
    "brand", "rating", "watchedlabel", "pricedrop", "popularityrank", "merchantcount",
}


def _first_number(raw: str) -> float | None:
    """Pull the leading numeric value out of a spec string.

    Handles Danish formats: "5200 mAh" -> 5200, "0,3 l" -> 0.3, "1.299,50" -> 1299.5,
    "1.299" -> 1299 (thousands dot). Single-dot decimals like "0.3" stay decimal.
    """
    if not raw:
        return None
    m = re.search(r"-?\d[\d.,]*", raw)
    if not m:
        return None
    s = m.group(0)
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")          # 1.299,50 -> 1299.50
    elif "," in s:
        s = s.replace(",", ".")                            # 4,5 -> 4.5
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")                             # 1.299 -> 1299 (thousands)
    try:
        return float(s)
    except ValueError:
        return None


def _comparable_specs(products: list[dict]) -> dict[str, dict[str, float]]:
    """{spec_key: {product_id: numeric_value}} for specs that >=2 products share
    with a parseable number and where the values are not all identical."""
    by_key: dict[str, dict[str, float]] = {}
    for p in products:
        for key, val in (p.get("specs") or {}).items():
            if key.lower() in _EXCLUDE_SPEC_KEYS:
                continue
            num = _first_number(str(val))
            if num is None:
                continue
            by_key.setdefault(key, {})[p["id"]] = num
    return {
        k: v for k, v in by_key.items()
        if len(v) >= 2 and len(set(v.values())) > 1
    }


def compute_value_signals(products: list[dict]) -> dict:
    """Comparative facts for a brief's product set.

    products: list of dicts with keys id, name, price_kr, specs (dict[str, str]).
    Returns a structure the generator prompt can cite directly. For a single-product
    set the comparative fields are empty (nothing to compare against) and only the
    price fact is populated - richer single-review context needs category aggregates,
    which the brief does not carry yet.
    """
    products = [p for p in products if p.get("id")]
    n = len(products)
    if n == 0:
        return {"set_size": 0, "per_product": {}}

    prices = [(p["id"], float(p.get("price_kr") or 0)) for p in products]
    priced = [(pid, pr) for pid, pr in prices if pr > 0]
    cheapest = min((pr for _, pr in priced), default=0.0)
    dearest = max((pr for _, pr in priced), default=0.0)
    median = round(statistics.median([pr for _, pr in priced]), 0) if priced else 0.0
    # rank 1 = cheapest; ties share the lower rank
    rank_order = sorted(priced, key=lambda x: x[1])
    price_rank = {pid: i + 1 for i, (pid, _) in enumerate(rank_order)}

    comparable = _comparable_specs(products)
    spec_present = {p["id"]: {k for k, v in (p.get("specs") or {}).items()
                              if k.lower() not in _EXCLUDE_SPEC_KEYS and str(v).strip()}
                    for p in products}

    per_product: dict[str, dict] = {}
    for p in products:
        pid = p["id"]
        pr = float(p.get("price_kr") or 0)
        leads: list[dict] = []
        for key, vals in comparable.items():
            if pid not in vals:
                continue
            if vals[pid] == max(vals.values()):
                leads.append({"spec": key, "value": p["specs"][key], "position": "highest"})
            elif vals[pid] == min(vals.values()):
                leads.append({"spec": key, "value": p["specs"][key], "position": "lowest"})
        # specs only this product has in the whole set
        others = set().union(*(s for q, s in spec_present.items() if q != pid)) if n > 1 else set()
        unique = sorted(spec_present[pid] - others) if n > 1 else []

        entry: dict = {"price_kr": pr}
        if pr > 0 and n > 1:
            entry.update({
                "price_rank": price_rank.get(pid),
                "price_rank_of": len(priced),
                "price_vs_cheapest_kr": round(pr - cheapest, 0),
                "price_position": (
                    "cheapest" if pr == cheapest else
                    "most_expensive" if pr == dearest else "mid"
                ),
            })
        if leads:
            entry["spec_leads"] = leads
        if unique:
            entry["unique_specs"] = unique
        per_product[pid] = entry

    return {
        "set_size": n,
        "currency": "kr",
        "price": {"min": cheapest, "max": dearest, "median": median} if priced else {},
        "per_product": per_product,
        "note": (
            "Comparative facts derived from this article's own products - cite them "
            "as your own analysis (e.g. 'billigst i testen', 'storst kapacitet'). "
            "Never cite platform watcher/rank/shop-count data."
        ),
    }
