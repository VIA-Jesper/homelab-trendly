"""
Pydantic models for the TestFlow pipeline.
All data structures used across the pipeline are defined here.
"""
import os
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime


class PRProduct(BaseModel):
    """A product fetched from PriceRunner."""
    id: str
    name: str
    price_min: float          # lowest merchant price in DKK
    price_max: float          # highest merchant price in DKK
    url: str                  # absolute pricerunner.dk product URL
    image_url: str            # CDN image URL
    rating: Optional[float] = None   # 0-5 star rating, if available
    review_count: Optional[int] = None
    merchant_count: int = 0   # number of merchants selling this product
    category_id: int = 0
    category_name: str = ""

    @property
    def affiliate_url(self) -> str:
        """Direct affiliate link - appends ref-site param."""
        ref = os.getenv("PRICERUNNER_AFFILIATE_ID", "")
        return f"{self.url}?ref-site={ref}"

    @property
    def price_display(self) -> str:
        """Human-readable price for article body (Danish format)."""
        return f"Fra {self.price_min:.0f} kr"


class YoastMeta(BaseModel):
    """Yoast SEO metadata for a WordPress post."""
    focus_keyword: str
    meta_description: str
    seo_title: str
    canonical: Optional[str] = None
    schema_type: str = "Article"


class AffiliateLink(BaseModel):
    """An affiliate link within an article."""
    anchor_text: str
    url: str
    product_name: str


class Article(BaseModel):
    """A complete article ready for publishing."""
    title: str
    slug: str
    excerpt: str = ""
    body_html: str
    yoast_meta: YoastMeta
    categories: list[str] = []     # Category names (resolved to WP IDs at publish time)
    tags: list[str] = []            # Tag names (resolved to WP IDs at publish time)
    featured_image_url: Optional[str] = None
    affiliate_links: list[AffiliateLink] = []
    status: str = "draft"           # Always draft - human clicks publish in WP Admin


class SiteConfig(BaseModel):
    """Configuration for a single WordPress site."""
    name: str         # used to look up WP_APP_PASSWORD_{NAME.upper()} in env
    url: str
    username: str


class PublishResult(BaseModel):
    """Result from publishing an article to WordPress."""
    post_id: int
    post_url: str
    published_at: datetime = Field(default_factory=datetime.utcnow)


class ComplianceReport(BaseModel):
    """Result from deterministic compliance audit."""
    passed: bool
    errors: list[str] = []
    warnings: list[str] = []
