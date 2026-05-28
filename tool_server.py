"""
TestFlow Tool Server - FastAPI HTTP interface for OpenClaw tools.

OpenClaw calls these endpoints via the TypeScript plugin.
Start with: poetry run task start   (or ./scripts/start.sh)
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="TestFlow Tool Server", version="0.1.0")

# ── Lazy imports (avoid startup errors if deps not installed yet) ──────────────

def get_pricerunner_client():
    from testflow.content.pricerunner import PriceRunnerClient
    return PriceRunnerClient()


def get_site_config(site_path: str):
    from testflow.models import SiteConfig
    path = Path(site_path)
    if not path.exists():
        raise FileNotFoundError(f"Site config not found: {site_path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SiteConfig(**data)


# ── Request models ────────────────────────────────────────────────────────────

class FetchProductsRequest(BaseModel):
    category_id: int
    limit: int = 10
    explicit_products: list[str] = []


class InjectComplianceRequest(BaseModel):
    html: str
    affiliate_id: str = ""
    partner_id: str = ""
    category_id: int = 0


class AuditRequest(BaseModel):
    html: str


class CreateDraftRequest(BaseModel):
    article: dict
    site: str = "sites/site-one.yaml"


class RecordRunRequest(BaseModel):
    run_id: str
    topic: str
    keyword: str
    category_id: int
    article_type: str
    status: str
    stats: dict = {}


class DiscoverCategoriesRequest(BaseModel):
    query: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/tools/fetch_products")
async def fetch_products(body: FetchProductsRequest):
    from testflow.orchestration.tools import fetch_products_by_category
    products = fetch_products_by_category(
        body.category_id,
        limit=body.limit,
        explicit_products=body.explicit_products or None,
    )
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "price_min": p.price_min,
                "price_max": p.price_max,
                "price_display": p.price_display,
                "url": p.url,
                "affiliate_url": p.affiliate_url,
                "image_url": p.image_url,
                "rating": p.rating,
                "review_count": p.review_count,
                "merchant_count": p.merchant_count,
                "category_id": p.category_id,
                "category_name": p.category_name,
            }
            for p in products
        ]
    }


@app.post("/tools/inject_compliance")
async def inject_compliance_endpoint(body: InjectComplianceRequest):
    from testflow.orchestration.tools import inject_compliance
    result = inject_compliance(
        body.html,
        affiliate_id=body.affiliate_id,
        partner_id=body.partner_id,
        category_id=body.category_id,
    )
    return result


@app.post("/tools/deterministic_audit")
async def deterministic_audit_endpoint(body: AuditRequest):
    from testflow.orchestration.tools import deterministic_audit
    report = deterministic_audit(body.html)
    return {"passed": report.passed, "errors": report.errors, "warnings": report.warnings}


@app.post("/tools/create_draft")
async def create_draft_endpoint(body: CreateDraftRequest):
    from testflow.models import Article, YoastMeta
    from testflow.orchestration.tools import create_draft

    article_data = body.article
    yoast_data = article_data.get("yoast_meta", {})
    article = Article(
        title=article_data["title"],
        slug=article_data["slug"],
        excerpt=article_data.get("excerpt", ""),
        body_html=article_data["body_html"],
        yoast_meta=YoastMeta(**yoast_data),
        categories=article_data.get("categories", []),
        tags=article_data.get("tags", []),
        featured_image_url=article_data.get("featured_image_url"),
    )
    site_config = get_site_config(body.site)
    result = create_draft(article, site_config)
    return {"post_id": result.post_id, "post_url": result.post_url}


@app.post("/tools/record_run")
async def record_run_endpoint(body: RecordRunRequest):
    from testflow.orchestration.tools import record_run
    record_run(
        body.run_id,
        site_name="",  # site_name resolved from context in production
        topic=body.topic,
        keyword=body.keyword,
        category_id=body.category_id,
        article_type=body.article_type,
        status=body.status,
    )
    return {"ok": True}


@app.get("/tools/published_titles")
async def published_titles(site_name: str, limit: int = 50):
    from testflow.orchestration.tools import get_published_titles
    titles = get_published_titles(site_name, limit=limit)
    return {"titles": titles}


@app.post("/tools/discover_categories")
async def discover_categories_endpoint(body: DiscoverCategoriesRequest):
    client = get_pricerunner_client()
    categories = client.discover_categories(body.query)
    return {"categories": categories}
