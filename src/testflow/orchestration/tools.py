"""
Orchestration tools - entry-point functions called by tool_server.py.

These are the only functions OpenClaw calls (via HTTP tool server).
None of them call an LLM.
"""
import os
import uuid
from pathlib import Path

import yaml

from testflow.models import Article, ComplianceReport, PRProduct, PublishResult, SiteConfig
from testflow.compliance.inject_compliance import inject_compliance as _inject_compliance
from testflow.compliance.rules import COMPLIANCE_RULES
from testflow.content.pricerunner import PriceRunnerClient, filter_by_explicit
from testflow.publisher.client import client_from_site_config
from testflow import db


# ── Product fetching ──────────────────────────────────────────────────────────

def fetch_products_by_category(
    category_id: int,
    limit: int = 10,
    explicit_products: list[str] | None = None,
) -> list[PRProduct]:
    """Fetch products from PriceRunner and optionally filter by explicit names."""
    client = PriceRunnerClient()
    products = client.fetch_products_by_category(category_id, limit=limit)
    if explicit_products:
        products = filter_by_explicit(products, explicit_products)
    return products


# ── Compliance transforms ─────────────────────────────────────────────────────

def inject_compliance(
    html: str,
    affiliate_id: str = "",
    partner_id: str = "",
    category_id: int = 0,
) -> dict:
    """Run all compliance transforms. Returns transformed HTML + count of transforms."""
    transformed, transforms_applied = _inject_compliance(
        html, affiliate_id, partner_id, category_id
    )
    return {"html": transformed, "transforms_applied": transforms_applied}


# ── Deterministic audit ───────────────────────────────────────────────────────

def deterministic_audit(html: str) -> ComplianceReport:
    """
    Rule-based compliance check on article HTML.

    Checks:
    - Affiliate disclosure present
    - All pricerunner.dk links have ref-site param
    - All pricerunner.dk links have rel="sponsored nofollow"
    - No prohibited claims in text
    - Widget present
    """
    from bs4 import BeautifulSoup
    errors: list[str] = []
    warnings: list[str] = []

    soup = BeautifulSoup(html, "html.parser")

    # 1. Disclosure check
    disclosure = soup.find("div", class_="affiliate-disclosure")
    if not disclosure:
        errors.append("Missing affiliate disclosure div (class='affiliate-disclosure')")

    # 2. PriceRunner links check
    domain = COMPLIANCE_RULES["affiliate_links"]["domain"]
    ref_param = COMPLIANCE_RULES["affiliate_links"]["ref_param"]
    required_rel = set(COMPLIANCE_RULES["affiliate_links"]["required_rel"])

    pr_links = [a for a in soup.find_all("a", href=True) if domain in a.get("href", "")]
    for link in pr_links:
        href = link.get("href", "")
        if f"{ref_param}=" not in href:
            errors.append(f"PriceRunner link missing {ref_param}=: {href[:80]}")
        link_rel = set(link.get("rel", []))
        if isinstance(link.get("rel"), str):
            link_rel = set(link.get("rel", "").split())
        missing_rel = required_rel - link_rel
        if missing_rel:
            errors.append(f"PriceRunner link missing rel={missing_rel}: {href[:80]}")

    # 3. Prohibited claims check
    text = soup.get_text().lower()
    for claim in COMPLIANCE_RULES["prohibited_claims"]:
        if claim.lower() in text:
            errors.append(f"Prohibited claim found: '{claim}'")

    # 4. Widget check
    has_widget = bool(
        soup.find("div", class_="pr-widget")
        or soup.find("script", src=lambda s: s and "partner.pricerunner.dk" in s)
    )
    if not has_widget:
        warnings.append("PriceRunner widget not found (pr-widget div or partner script)")

    return ComplianceReport(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ── WordPress publishing ──────────────────────────────────────────────────────

def create_draft(article: Article, site_config: SiteConfig) -> PublishResult:
    """Create a WordPress draft post. Never publishes live."""
    client = client_from_site_config(site_config)
    return client.create_post(article)


# ── State database ────────────────────────────────────────────────────────────

def record_run(
    run_id: str, site_name: str, topic: str, keyword: str,
    category_id: int, article_type: str, status: str,
    post_id: int | None = None, post_url: str | None = None,
    duration_sec: float | None = None,
) -> None:
    db.record_run(
        run_id, site_name, topic, keyword,
        category_id, article_type, status,
        post_id, post_url, duration_sec,
    )


def record_review_attempt(
    run_id: str, phase: str, attempt: int, passed: bool,
    score: float | None, feedback: str | None,
) -> None:
    db.record_review_attempt(run_id, phase, attempt, passed, score, feedback)


def get_published_titles(site_name: str, limit: int = 50) -> list[str]:
    return db.get_published_titles(site_name, limit=limit)


def get_published_count(site_name: str, since_days: int = 7) -> int:
    return db.get_published_count(site_name, since_days=since_days)


def generate_run_id() -> str:
    return str(uuid.uuid4())
