"""
WordPress publisher — converts article markdown to HTML and posts via WP REST API.

Uses:
  - markdown library (python-markdown) for markdown→HTML conversion.
    Raw HTML blocks (widget embeds, figure tags) pass through unchanged.
  - httpx for async HTTP calls.
  - Rank Math REST API extension fields for SEO metadata.

Category resolution:
  Looks up WP category by slug; creates it if missing.
  Category name comes from brief.category.
"""

import base64
import re

import httpx
import markdown as _md_lib

from services.brief_builder import ContentBrief, get_site_config

_DANISH = [("æ", "ae"), ("ø", "oe"), ("å", "aa"), ("Æ", "Ae"), ("Ø", "Oe"), ("Å", "Aa")]


def slugify(text: str) -> str:
    for src, dst in _DANISH:
        text = text.replace(src, dst)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def markdown_to_html(article_md: str) -> str:
    """
    Convert article markdown (which may contain raw HTML widget blocks) to HTML.
    The markdown library preserves raw HTML blocks unchanged by design.
    """
    return _md_lib.markdown(article_md, extensions=["extra"])


async def _resolve_category(
    client: httpx.AsyncClient,
    base_url: str,
    auth: str,
    category_name: str,
) -> int | None:
    """Return WP category ID for category_name, creating the category if it doesn't exist."""
    slug = slugify(category_name)
    r = await client.get(
        f"{base_url}/wp-json/wp/v2/categories",
        params={"slug": slug, "_fields": "id,name,slug"},
        headers={"Authorization": auth},
    )
    if r.status_code == 200:
        cats = r.json()
        if cats:
            return cats[0]["id"]

    r = await client.post(
        f"{base_url}/wp-json/wp/v2/categories",
        json={"name": category_name, "slug": slug},
        headers={"Authorization": auth, "Content-Type": "application/json"},
    )
    if r.status_code in (200, 201):
        return r.json().get("id")
    return None


async def publish_to_wordpress(
    article_html: str,
    brief: ContentBrief,
    seo: dict,
    wp_status: str = "draft",
) -> dict:
    """
    Create a WP post. Returns {"post_id": int, "post_url": str, "wp_status": str}.
    Raises RuntimeError on WP API failure.
    """
    site_cfg = get_site_config(brief.site_key)
    base_url = site_cfg.wp_url.rstrip("/")
    auth = "Basic " + base64.b64encode(
        f"{site_cfg.wp_user}:{site_cfg.wp_pass}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=30.0) as client:
        category_id = await _resolve_category(client, base_url, auth, brief.category)

        title = seo.get("title") or (brief.products[0].name if brief.products else "")
        post_slug = slugify(seo.get("slug") or seo.get("title") or brief.category)

        post_data: dict = {
            "title": title,
            "content": article_html,
            "slug": post_slug,
            "status": wp_status,
            "meta": {
                "rank_math_title": seo.get("title", ""),
                "rank_math_description": seo.get("description", ""),
                "rank_math_focus_keyword": seo.get("focus_keyword", ""),
            },
        }
        if category_id:
            post_data["categories"] = [category_id]

        r = await client.post(
            f"{base_url}/wp-json/wp/v2/posts",
            json=post_data,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"WP API {r.status_code}: {r.text[:400]}")

        post = r.json()
        return {
            "post_id": post["id"],
            "post_url": post.get("link", ""),
            "wp_status": post.get("status", wp_status),
        }
