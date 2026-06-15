"""
freeze_eval_briefs.py - Build the frozen brief set for offline prompt eval.

WHY
  The prompt-eval harness (scripts/eval_prompts.py) runs the writer over a FIXED
  set of briefs so a prompt/model/system-prompt change is measured on identical
  inputs (run A vs run B). This script produces that set under
  evals/briefs/<type>/*.json. Each file is a job.context dict
  ({"brief": {...}, "article_type": "..."}) - exactly what the pipeline hands the
  writer as `context`, so the harness feeds the writer the same shape production does.

PROVENANCE
  review/      Real single-product-review briefs extracted from the local DB
               (the articles generated during the system check). Fully real.
  comparison/  Built via brief_builder.build_brief_for_comparison from real
               same-category product PAIRS pulled from those briefs. Real products,
               real structure.
  hero/        Built via brief_builder.build_brief_for_hero. We only have 3 real
               robotstoevsuger products - below the 5-product hero minimum - so the
               set is padded with realistic same-category FIXTURE products (ids
               prefixed pr_fixture_). Refresh from real data once a hero job runs.

  Specs are sparse (platform-meta only) because spec enrichment is still parked, so
  value_signals carry mostly price. That is intentional: the eval measures the
  writer against the briefs we actually produce today.

Re-run any time (overwrites deterministically; only brief_id uuids vary):
    .venv/Scripts/python.exe scripts/freeze_eval_briefs.py
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))

from services.brief_builder import build_brief_for_comparison, build_brief_for_hero  # noqa: E402
from services.pricerunner_client import RawProduct  # noqa: E402

_DB = _ROOT / "trendly_local.db"
_OUT = _ROOT / "evals" / "briefs"
_SITE = "hus"


def _slug(s: str) -> str:
    s = s.lower().replace("ø", "oe").replace("å", "aa").replace("æ", "ae")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:50] or "brief"


def _strip_refsite(url: str) -> str:
    """Remove the ?refsite=/&refsite= the builder appends, so re-running a brief
    back through a builder does not double the param."""
    for sep in ("?refsite=", "&refsite="):
        if sep in url:
            return url.split(sep)[0]
    return url


def _raw_from_brief(ctx: dict) -> RawProduct:
    """Reconstruct a RawProduct from a stored single-product-review job.context."""
    brief = ctx["brief"]
    p = brief["products"][0]
    img = (brief.get("images") or [{}])[0]
    return RawProduct(
        id=p["id"],
        name=p["name"],
        category=p["category"],
        price_kr=float(p["price_kr"]),
        retailer=p["retailer"],
        affiliate_url=_strip_refsite(p["affiliate_url"]),
        image_url=img.get("url", ""),
        popularity_score=0.0,
        out_of_stock=False,
        specs=p.get("specs") or {},
    )


def _write(type_dir: str, slug: str, context: dict) -> None:
    out_dir = _OUT / type_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.json"
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  WROTE {path.relative_to(_ROOT)}")


def _ctx(brief) -> dict:
    """Wrap a ContentBrief as the job.context shape the harness consumes."""
    return {"brief": brief.model_dump(), "article_type": brief.article_type}


# Realistic same-category robotstoevsuger fixtures to top a hero brief up to 5.
# Marked pr_fixture_ so they are never mistaken for live products.
_HERO_PADDING = [
    RawProduct(
        id="pr_fixture_roborock_s8maxv", name="Roborock S8 MaxV Ultra",
        category="robotstoevsugere", price_kr=8999.0, retailer="PriceRunner",
        affiliate_url="https://www.pricerunner.dk/pl/1613-3400000001/Robotstoevsugere/Roborock-S8-MaxV-Ultra/",
        image_url="", popularity_score=0.0, out_of_stock=False,
        specs={"brand": "Roborock"},
    ),
    RawProduct(
        id="pr_fixture_roborock_qrevo", name="Roborock Q Revo",
        category="robotstoevsugere", price_kr=4499.0, retailer="PriceRunner",
        affiliate_url="https://www.pricerunner.dk/pl/1613-3400000002/Robotstoevsugere/Roborock-Q-Revo/",
        image_url="", popularity_score=0.0, out_of_stock=False,
        specs={"brand": "Roborock"},
    ),
]


def main() -> None:
    if not _DB.exists():
        print(f"ERROR: DB not found at {_DB}")
        sys.exit(1)

    con = sqlite3.connect(_DB)
    rows = con.execute("SELECT context FROM jobs ORDER BY created_at").fetchall()
    con.close()

    reviews = []
    for (ctx_json,) in rows:
        ctx = json.loads(ctx_json) if ctx_json else {}
        if ctx.get("article_type") == "single-product-review" and ctx.get("brief", {}).get("products"):
            reviews.append(ctx)

    if not reviews:
        print("ERROR: no single-product-review briefs in DB - nothing to seed from.")
        sys.exit(1)

    print(f"Found {len(reviews)} real review brief(s).")

    # review/ - straight copies of the real contexts
    print("review/")
    for ctx in reviews:
        name = ctx["brief"]["products"][0]["name"]
        _write("review", _slug(name), ctx)

    raws = [_raw_from_brief(c) for c in reviews]

    # comparison/ - real same-category pairs
    print("comparison/")
    pairs = [(0, 1)]
    if len(raws) >= 3:
        pairs.append((0, 2))
    for i, j in pairs:
        brief = build_brief_for_comparison([raws[i], raws[j]], _SITE)
        slug = _slug(f"{raws[i].name}-vs-{raws[j].name}")
        _write("comparison", slug, _ctx(brief))

    # hero/ - real products + realistic fixtures to reach the 5-product minimum
    print("hero/")
    hero_products = raws + _HERO_PADDING
    hero_products = hero_products[:10]  # builder caps at 10
    brief = build_brief_for_hero(hero_products, _SITE)
    _write("hero", _slug(f"bedste-{brief.category_slug}"), _ctx(brief))

    print("\nDone. Frozen brief set written to evals/briefs/.")


if __name__ == "__main__":
    main()
