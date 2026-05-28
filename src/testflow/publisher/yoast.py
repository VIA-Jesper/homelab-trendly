"""
Yoast SEO bridge helper.

Thin wrapper around the Yoast REST Bridge WordPress plugin endpoints.
The bridge plugin exposes /wp-json/yoast-bridge/v1/post/{id}/meta
for reading and writing Yoast SEO fields.

Most usage goes through WordPressClient.set_yoast_meta() - this module
provides a standalone helper for reading Yoast data without a full client.
"""
import httpx
from testflow.models import YoastMeta


def read_yoast_meta(base_url: str, post_id: int, auth_header: str) -> YoastMeta | None:
    """
    Read Yoast SEO metadata for a post via the Yoast REST Bridge.

    Args:
        base_url: WordPress site base URL
        post_id: WordPress post ID
        auth_header: Authorization header value (e.g. "Basic <base64>")

    Returns:
        YoastMeta if successful, None if bridge plugin not installed or post not found.
    """
    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/wp-json/yoast-bridge/v1/post/{post_id}/meta",
            headers={"Authorization": auth_header},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return YoastMeta(
            focus_keyword=data.get("focus_keyword", ""),
            meta_description=data.get("meta_description", ""),
            seo_title=data.get("seo_title", ""),
            canonical=data.get("canonical"),
            schema_type=data.get("schema_type", "Article"),
        )
    except Exception:
        return None
