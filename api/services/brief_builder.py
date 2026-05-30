"""
Brief builder — assembles a ContentBrief from PriceRunner product data.

WHY THIS EXISTS
  The generator agent needs a structured brief (product data + writing rules +
  compliance rules) rather than raw API responses. The brief is the contract
  between data fetching and content generation — it normalises everything the
  agent needs into one JSON blob that goes into job.context["brief"].

  This is a Python port of archive/src/services/brief-builder.ts, simplified
  for the single-product-review path. Category-based brief building (for roundups,
  hero articles, etc.) can be added later following the same pattern.

WHY PYDANTIC MODELS
  We already have pydantic in the stack (FastAPI uses it). Pydantic models give us
  free JSON serialisation (.model_dump()), validation on construction, and clear
  field documentation. The TS implementation used Zod for the same reason.

SITE CONFIG
  Each site has different WP credentials, a PriceRunner partner ID, and writing
  tone preferences. Config lives here for now — move to DB or Settings if sites
  proliferate. The partner ID is required for widget rendering; without it the
  widget inserter falls back to a plain HTML card.

  Site keys match the env var prefix convention: "hus" = husforbegyndere.dk,
  "shelter" = shelterguru.dk. Add new sites by extending SITE_CONFIGS.
"""

import uuid
from typing import Optional

from pydantic import BaseModel

from config import settings
from services.pricerunner_client import RawProduct


# ─── Site configuration ────────────────────────────────────────────────────────

class SiteConfig(BaseModel):
    site_key: str
    domain: str
    pricerunner_partner_id: str
    pricerunner_country: str = "DK"
    wp_url: str
    wp_user: str
    wp_pass: str
    tone: str = "analytical"          # analytical | friendly | neutral
    min_words: int = 800
    max_words: int = 1400
    include_pros_cons: bool = True
    include_verdict: bool = True


# Partner IDs and credentials are loaded from Settings (which reads from .env).
# See config.py for the field definitions.
SITE_CONFIGS: dict[str, SiteConfig] = {
    "hus": SiteConfig(
        site_key="hus",
        domain="husforbegyndere.dk",
        pricerunner_partner_id=settings.pr_hus_partner_id,
        wp_url=settings.wp_hus_url,
        wp_user=settings.wp_hus_user,
        wp_pass=settings.wp_hus_pass,
        tone="friendly",
        min_words=700,
        max_words=1200,
    ),
}


def get_site_config(site_key: str) -> SiteConfig:
    cfg = SITE_CONFIGS.get(site_key)
    if cfg is None:
        raise ValueError(
            f"Unknown site key '{site_key}'. "
            f"Known keys: {list(SITE_CONFIGS.keys())}"
        )
    return cfg


# ─── Brief data models ─────────────────────────────────────────────────────────

class ProductBrief(BaseModel):
    """
    Slimmed-down product representation for the generator agent.
    imageUrl is excluded — that lives in ImageRef. popularityScore and outOfStock
    are also excluded since the agent shouldn't reason about internal scoring.
    """
    id: str            # "pr_3332774746"
    name: str
    category: str
    price_kr: float
    retailer: str
    affiliate_url: str
    specs: dict[str, str]


class ImageRef(BaseModel):
    product_id: str
    url: str
    alt: str
    caption: str


class WritingRules(BaseModel):
    tone: str
    min_words: int
    max_words: int
    include_pros_cons: bool
    include_verdict: bool


class ComplianceRules(BaseModel):
    """
    Rules the generator must follow for legal/trust reasons.
    requireDisclosure=False because we use a site-wide disclosure rather than
    per-article — the generator still includes it but QA doesn't fail without it.
    """
    require_disclosure: bool
    disclosure_phrases: list[str]
    forbidden_superlatives: list[str]


class ContentBrief(BaseModel):
    """
    Full brief passed to the generator agent as job.context["brief"].
    Every field here is referenced by name in the generator prompt — don't
    rename fields without updating the prompt accordingly.
    """
    brief_id: str
    site_key: str
    category: str
    products: list[ProductBrief]
    images: list[ImageRef]
    writing_rules: WritingRules
    compliance: ComplianceRules
    article_type: str    # always "single-product-review" for URL-based jobs
    article_hook: str    # one-line angle for the article, e.g. "Er det værd at betale mere?"


# ─── Default compliance rules ──────────────────────────────────────────────────
# Kept as a module-level constant since they apply to all Danish affiliate sites.
_DEFAULT_COMPLIANCE = ComplianceRules(
    require_disclosure=False,
    disclosure_phrases=[
        "indeholder affiliatelinks",
        "vi tjener kommission",
        "annonce",
        "reklame",
    ],
    forbidden_superlatives=[
        "bedste på markedet",
        "billigst i danmark",
        "nr. 1 valg",
        "absolut bedst",
    ],
)


# ─── Brief construction ────────────────────────────────────────────────────────

def _build_article_hook(product: RawProduct) -> str:
    """
    Generate a one-line angle for the article based on available product signals.
    Mirrors the article hook logic in archive/src/services/article-classifier.ts.
    """
    watched = product.specs.get("watchedLabel")
    price_drop = product.specs.get("priceDrop")
    rank = product.specs.get("popularityRank")

    if watched:
        return f"{product.name}: Er det den robot {watched} danskere holder øje med en god grund til?"
    if price_drop:
        return f"{product.name}: Ny lavpris — er det nu du skal slå til?"
    if rank == "1":
        return f"{product.name}: Kategoritopper — men holder den hvad den lover?"
    return f"{product.name} anmeldelse — er det pengene værd?"


def build_brief_for_product(product: RawProduct, site_key: str) -> ContentBrief:
    """
    Assemble a ContentBrief for a single-product-review article.

    This is the entry point for URL-based job creation. The brief is stored as
    job.context["brief"] and passed to the generator agent at every pipeline step.

    Why single article type:
      When a user provides a specific product URL they want THAT product reviewed —
      not compared to a category. The "single-product-review" type forces a focused
      1-product article rather than the classifier making a different call.
    """
    site = get_site_config(site_key)

    product_brief = ProductBrief(
        id=product.id,
        name=product.name,
        category=product.category,
        price_kr=product.price_kr,
        retailer=product.retailer,
        affiliate_url=product.affiliate_url,
        specs=product.specs,
    )

    brand = product.specs.get("brand", "")
    alt_text = f"{product.name} — {brand}".strip(" —") if brand else product.name
    caption = f"{product.name} hos {product.retailer} — {product.price_kr:,.0f} kr.".replace(",", ".")

    image_ref = ImageRef(
        product_id=product.id,
        url=product.image_url,
        alt=alt_text,
        caption=caption,
    )

    writing_rules = WritingRules(
        tone=site.tone,
        min_words=site.min_words,
        max_words=site.max_words,
        include_pros_cons=site.include_pros_cons,
        include_verdict=site.include_verdict,
    )

    return ContentBrief(
        brief_id=str(uuid.uuid4()),
        site_key=site_key,
        category=product.category,
        products=[product_brief],
        images=[image_ref],
        writing_rules=writing_rules,
        compliance=_DEFAULT_COMPLIANCE,
        article_type="single-product-review",
        article_hook=_build_article_hook(product),
    )
