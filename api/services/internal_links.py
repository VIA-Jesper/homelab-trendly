"""
internal_links.py - build a "related articles" cluster for an article (Phase 2D).

WHY
  Internal links between articles on the same topic build topical authority and
  spread crawl/link equity - a cheap, deterministic ranking lever. We link an
  article to other published articles in the SAME category (the cluster), sourced
  from the coverage ledger (which knows every article's slug + category).

PURE / STDLIB-ONLY
  This module only formats markdown from candidates a caller supplies. The DB query
  (which articles exist, are published, share the category) lives in
  services.coverage.related_articles, so this stays unit-testable with no DB.
"""


def deslugify(slug: str) -> str:
    """Fallback anchor text from a slug: 'bedste-robotstoevsugere' -> 'Bedste robotstoevsugere'.
    Used only when the coverage row has no primary_keyword to use as the anchor."""
    words = (slug or "").replace("-", " ").split()
    if not words:
        return ""
    return " ".join(words).capitalize()


def build_related_section(
    candidates: list[dict],
    domain: str,
    heading: str = "Læs også",
    max_links: int = 4,
) -> str:
    """Markdown '## Læs også' block linking to related articles, or "" if none.

    candidates: list of {"slug": str, "title": str | None}. `title` (the coverage
    row's primary_keyword) is preferred as anchor text; falls back to deslugify(slug).
    Returns markdown to append to the article body before publish.
    """
    seen: set[str] = set()
    items: list[str] = []
    for c in candidates:
        slug = (c.get("slug") or "").strip().strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        anchor = (c.get("title") or "").strip() or deslugify(slug)
        items.append(f"- [{anchor}](https://{domain}/{slug}/)")
        if len(items) >= max_links:
            break
    if not items:
        return ""
    return f"\n\n## {heading}\n\n" + "\n".join(items) + "\n"
