"""
WordPress REST API client.

Creates draft posts, resolves/creates categories and tags, sideloads images,
and sets Yoast SEO metadata via the Yoast REST Bridge plugin.

Never publishes live - always creates status=draft.
"""
import os
from base64 import b64encode
from datetime import datetime

import httpx

from testflow.models import Article, PublishResult, SiteConfig


class WordPressClient:
    def __init__(self, site_url: str, username: str, app_password: str):
        self.base = site_url.rstrip("/")
        creds = b64encode(f"{username}:{app_password}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }
        self._session = httpx.Client(timeout=30, headers=self._headers)

    # ── Category & Tag helpers ────────────────────────────────────────────────

    def get_or_create_category(self, name: str) -> int:
        """Return existing category ID or create and return new one."""
        resp = self._session.get(
            f"{self.base}/wp-json/wp/v2/categories",
            params={"search": name},
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return results[0]["id"]
        resp = self._session.post(
            f"{self.base}/wp-json/wp/v2/categories",
            json={"name": name},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def get_or_create_tag(self, name: str) -> int:
        """Return existing tag ID or create and return new one."""
        resp = self._session.get(
            f"{self.base}/wp-json/wp/v2/tags",
            params={"search": name},
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return results[0]["id"]
        resp = self._session.post(
            f"{self.base}/wp-json/wp/v2/tags",
            json={"name": name},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # ── Image sideload ────────────────────────────────────────────────────────

    def sideload_image(self, image_url: str, alt_text: str = "") -> int | None:
        """
        Sideload an image from a URL to the WP Media Library.
        Returns media attachment ID, or None if sideload fails.
        """
        try:
            resp = self._session.post(
                f"{self.base}/wp-json/wp/v2/media",
                headers={
                    **self._headers,
                    "Content-Type": "application/json",
                },
                json={"source_url": image_url, "alt_text": alt_text},
            )
            resp.raise_for_status()
            return resp.json()["id"]
        except Exception:
            return None

    # ── Post creation ─────────────────────────────────────────────────────────

    def set_yoast_meta(self, post_id: int, meta) -> None:
        """Write Yoast SEO fields via the Yoast REST Bridge plugin."""
        payload = {
            "focus_keyword": meta.focus_keyword,
            "meta_description": meta.meta_description,
            "seo_title": meta.seo_title,
        }
        if meta.canonical:
            payload["canonical"] = str(meta.canonical)
        if meta.schema_type:
            payload["schema_type"] = meta.schema_type
        resp = self._session.post(
            f"{self.base}/wp-json/yoast-bridge/v1/post/{post_id}/meta",
            json=payload,
        )
        resp.raise_for_status()

    def create_post(self, article: Article) -> PublishResult:
        """
        Create a WordPress draft post from an Article.
        Resolves category/tag names to IDs.
        Sideloads featured image if provided.
        Sets Yoast meta after post creation.
        Always creates as status=draft.
        """
        category_ids = [self.get_or_create_category(c) for c in article.categories]
        tag_ids = [self.get_or_create_tag(t) for t in article.tags]

        featured_media_id = None
        if article.featured_image_url:
            featured_media_id = self.sideload_image(
                article.featured_image_url, article.title
            )

        post_payload: dict = {
            "title": article.title,
            "slug": article.slug,
            "content": article.body_html,
            "excerpt": article.excerpt,
            "status": "draft",
            "categories": category_ids,
            "tags": tag_ids,
        }
        if featured_media_id:
            post_payload["featured_media"] = featured_media_id

        resp = self._session.post(
            f"{self.base}/wp-json/wp/v2/posts",
            json=post_payload,
        )
        resp.raise_for_status()
        post_data = resp.json()
        post_id = post_data["id"]
        post_url = post_data.get("link", f"{self.base}/?p={post_id}")

        # Set Yoast SEO metadata
        self.set_yoast_meta(post_id, article.yoast_meta)

        return PublishResult(
            post_id=post_id,
            post_url=post_url,
            published_at=datetime.utcnow(),
        )


def client_from_site_config(site: SiteConfig) -> WordPressClient:
    """Build a WordPressClient from a SiteConfig, loading the app password from env."""
    env_key = f"WP_APP_PASSWORD_{site.name.upper()}"
    app_password = os.getenv(env_key)
    if not app_password:
        raise ValueError(f"Missing environment variable: {env_key}")
    return WordPressClient(str(site.url), site.username, app_password)
