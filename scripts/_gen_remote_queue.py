"""
_gen_remote_queue.py — Generate data/queue-remote.json for a remote Trendly instance.

This script knows which categories the LOCAL system has already covered, and generates
a prioritized job list for a remote instance that has a clean/empty DB.

Run from the repo root:
  python scripts/_gen_remote_queue.py
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

JSONL = Path("data/hot-products.jsonl")
OUT   = Path("data/queue-remote.json")

CATEGORY_SLUG = {
    "19": "stovsugere", "81": "frituregryder-airfryere", "82": "kaffemaskiner",
    "250": "ismaskiner", "14": "vaskemaskiner", "1613": "robotstoevsugere",
    "1595": "robotplaeneklippere", "335": "grill", "120": "havemaskiner",
    "638": "hojtryks-hedvandsrensere", "345": "elvaerktoej", "1258": "bore-skruemaskiner",
    "1260": "elsave", "499": "havemoebel", "119": "plaeneklippere",
    "1290": "trampoliner", "541": "pools", "1388": "spabade-vildmarksbade",
    "1611": "havetraktorer", "84": "blendere", "1244": "roeremaskiner-foodprocessorer",
    "17": "toerretumblere", "101": "komfurer", "105": "ovne", "106": "kogeplader",
    "348": "haveredskaber",
}

# Articles already published on the LOCAL system — remote should avoid these categories.
# Count = number of articles the local system has published in that category.
LOCAL_PUBLISHED: dict[str, int] = {
    "robotplaeneklippere":    1,  # Segway Navimow i105E
    "stovsugere":             2,  # Dyson V15 + BISSELL/Kärcher comparison
    "grill":                  1,  # Weber Q 3200N+
    "robotstoevsugere":       2,  # Dreame X50 Ultra Complete + comparison hero
    "ismaskiner":             1,  # Ninja CREAMi Deluxe
    "havemoebel":             1,  # Fatboy Headdemock
    "hojtryks-hedvandsrensere": 1, # Nilfisk Premium 190-12
    "havetraktorer":          1,  # Husqvarna TS 112
}

HERO_MIN = 5
HERO_MAX = 7


def watcher_score(w) -> int:
    if not w:
        return 0
    try:
        return int(str(w).replace("+", "").strip())
    except ValueError:
        return 0


def score_product(p: dict) -> float:
    s = 0.0
    w = watcher_score(p.get("watchers"))
    if w >= 200:   s += 40
    elif w >= 100: s += 30
    elif w >= 50:  s += 20
    elif w > 0:    s += 10
    r = p.get("rank")
    if r is not None:
        if r == 1:    s += 30
        elif r == 2:  s += 25
        elif r == 3:  s += 20
        elif r <= 10: s += 10
    return s


def main():
    # Read JSONL, dedupe by product_url keeping highest-scored entry
    best: dict[str, tuple[float, dict]] = {}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        p = json.loads(line)
        if not p.get("product_url"):
            continue
        if p.get("out_of_stock"):
            continue
        url = p["product_url"]
        s = score_product(p)
        if url not in best or s > best[url][0]:
            best[url] = (s, p)

    # Group by slug
    by_slug: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for url, (s, p) in best.items():
        cat_id = (p.get("category_id") or "").lstrip("cl")
        slug = CATEGORY_SLUG.get(cat_id)
        if not slug:
            continue
        by_slug[slug].append((s, p))

    for slug in by_slug:
        by_slug[slug].sort(key=lambda x: x[0], reverse=True)

    # Build job plan
    jobs = []
    used_slugs: set[str] = set()

    # Pass 1: hero opportunities — 0 locally published AND 5+ candidates
    for slug, bucket in sorted(by_slug.items(), key=lambda kv: kv[1][0][0], reverse=True):
        pub = LOCAL_PUBLISHED.get(slug, 0)
        if pub > 0:
            continue
        if len(bucket) < HERO_MIN:
            continue
        top = bucket[:HERO_MAX]
        names  = [p["name"] for _, p in top]
        urls   = [p["product_url"] for _, p in top]
        cat_display = top[0][1].get("category_name") or slug
        jobs.append({
            "priority":     len(jobs) + 1,
            "article_type": "hero",
            "category":     slug,
            "category_display": cat_display,
            "product_urls": urls,
            "product_names": names,
            "reasoning": (
                f"Hero: {len(bucket)} candidates in '{slug}', 0 existing articles. "
                f"Top: {', '.join(names[:3])}..."
            ),
        })
        used_slugs.add(slug)

    # Pass 2: top single per category — including locally-covered ones (remote starts fresh)
    for slug, bucket in sorted(by_slug.items(), key=lambda kv: kv[1][0][0], reverse=True):
        if slug in used_slugs:
            continue
        s, p = bucket[0]
        cat_display = p.get("category_name") or slug
        price = p.get("price_dkk")
        price_str = f"{price:,.0f} kr" if price else "?"
        watch = p.get("watchers") or "-"
        rank  = p.get("rank") or "?"
        jobs.append({
            "priority":     len(jobs) + 1,
            "article_type": "single-product-review",
            "category":     slug,
            "category_display": cat_display,
            "product_urls": [p["product_url"]],
            "product_names": [p["name"]],
            "reasoning": (
                f"Score {s:.0f} — rank {rank}, {watch} watchers, {price_str}"
            ),
        })
        used_slugs.add(slug)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Prioritized job list for a remote Trendly instance with a clean DB. "
            "Heroes first (uncovered categories with 5+ candidates), "
            "then top singles per category. "
            "POST each job to /api/v1/jobs/from-products with site_key='hus'."
        ),
        "local_published_categories": LOCAL_PUBLISHED,
        "jobs": jobs,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(jobs)} jobs to {OUT}")
    print()
    print("Summary:")
    heroes  = [j for j in jobs if j["article_type"] == "hero"]
    singles = [j for j in jobs if j["article_type"] == "single-product-review"]
    print(f"  Hero bundles:  {len(heroes)}")
    print(f"  Singles:       {len(singles)}")
    print()
    for j in jobs[:15]:
        atype = "HERO  " if j["article_type"] == "hero" else "SINGLE"
        names_preview = ", ".join(j["product_names"][:2])
        if len(j["product_names"]) > 2:
            names_preview += f" +{len(j['product_names'])-2}"
        print(f"  {j['priority']:>2}. {atype}  {j['category']:<35} {names_preview[:50]}")


if __name__ == "__main__":
    main()
