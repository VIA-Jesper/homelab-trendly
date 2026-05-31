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
import mimetypes
import re
from urllib.parse import urlparse

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


def _stamp_refsite(html: str, partner_id: str) -> str:
    """Add ?refsite= to every PriceRunner href that doesn't already have it."""
    def _add(m: re.Match) -> str:
        url = m.group(1)
        if "refsite=" in url:
            return m.group(0)
        sep = "&" if "?" in url else "?"
        return f'href="{url}{sep}refsite={partner_id}"'

    return re.sub(r'href="(https?://(?:www\.)?pricerunner\.[^"]+)"', _add, html)


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


async def _upload_featured_image(
    client: httpx.AsyncClient,
    base_url: str,
    auth: str,
    image_url: str,
    alt: str,
    caption: str,
) -> int | None:
    """Download image from URL and upload to WP media library. Returns media ID or None."""
    try:
        r = await client.get(image_url, follow_redirects=True, timeout=20.0)
        if r.status_code != 200:
            return None
        image_bytes = r.content
        content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        filename = urlparse(image_url).path.split("/")[-1] or f"featured{ext}"
        r = await client.post(
            f"{base_url}/wp-json/wp/v2/media",
            content=image_bytes,
            headers={
                "Authorization": auth,
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
        if r.status_code not in (200, 201):
            return None
        media = r.json()
        media_id = media.get("id")
        if media_id and (alt or caption):
            await client.post(
                f"{base_url}/wp-json/wp/v2/media/{media_id}",
                json={"alt_text": alt, "caption": caption},
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
        return media_id
    except Exception:
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

    article_html = _stamp_refsite(article_html, site_cfg.pricerunner_partner_id)

    async with httpx.AsyncClient(timeout=30.0) as client:
        category_id = await _resolve_category(client, base_url, auth, brief.category)

        # Resolve featured image from brief using seo.featured_image_product_id
        featured_media_id: int | None = None
        featured_product_id = seo.get("featured_image_product_id")
        if featured_product_id and brief.images:
            img = next((i for i in brief.images if i.product_id == featured_product_id), brief.images[0])
        elif brief.images:
            img = brief.images[0]
        else:
            img = None
        if img:
            featured_media_id = await _upload_featured_image(
                client, base_url, auth, img.url, img.alt, img.caption
            )

        title = seo.get("title") or (brief.products[0].name if brief.products else "")
        post_slug = slugify(seo.get("slug") or seo.get("title") or brief.category)

        post_data: dict = {
            "title": title,
            "content": article_html,
            "slug": post_slug,
            "status": wp_status,
            "comment_status": "closed",
            "_yoast_wpseo_title": seo.get("title", ""),
            "_yoast_wpseo_metadesc": seo.get("description", ""),
            "_yoast_wpseo_focuskw": seo.get("focus_keyword", ""),
        }
        if category_id:
            post_data["categories"] = [category_id]
        if featured_media_id:
            post_data["featured_media"] = featured_media_id

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
