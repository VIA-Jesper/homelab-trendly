"""
Sequential pipeline coordinator.

This is the reference pipeline for CLI / testing use.
In production, OpenClaw drives all reasoning phases itself.
The openclaw_phase() placeholder represents "OpenClaw reads context and produces JSON".

See skills/affiliate-pipeline.md for the authoritative pipeline instructions.
"""
from testflow.models import Article, PublishResult, SiteConfig
from testflow.compliance.inject_compliance import inject_compliance
from testflow.compliance.rules import COMPLIANCE_RULES
from testflow.content.pricerunner import PriceRunnerClient, filter_by_explicit
from testflow.orchestration.tools import (
    deterministic_audit,
    create_draft,
    record_run,
    record_review_attempt,
    get_published_titles,
    generate_run_id,
)
from testflow.orchestration.templates import load_template
from testflow.orchestration.prompts import (
    build_brief_context,
    build_brief_review_context,
    build_article_context,
    build_article_review_context,
    build_seo_context,
    build_cro_context,
    build_optimization_review_context,
)
from testflow.orchestration.logging import log
import os

BRIEF_MAX_RETRIES = 2
ARTICLE_MAX_RETRIES = 3
PASS_SCORE = 7


def openclaw_phase(context: str) -> dict:
    """
    Placeholder: represents OpenClaw reading a context string and producing JSON.

    In production, OpenClaw IS the one calling these Python functions and doing
    reasoning between calls. This function exists for CLI/reference use only.
    Replace with a direct API call for offline testing if needed.
    """
    raise NotImplementedError(
        "openclaw_phase() is a placeholder. "
        "In production, OpenClaw drives all reasoning. "
        "For CLI testing, implement an LLM call here."
    )


def run_article_pipeline(
    article_type: str,
    topic: str,
    keyword: str,
    category_id: int,
    explicit_products: list[str],
    site_config: SiteConfig,
) -> PublishResult | None:
    """
    Full sequential pipeline coordinator.
    OpenClaw drives this in production - this is the CLI/reference implementation.
    """
    client = PriceRunnerClient()
    products = client.fetch_products_by_category(category_id, limit=10)
    if explicit_products:
        products = filter_by_explicit(products, explicit_products)
    if not products:
        log.error(f"No products found for category {category_id} (keyword: '{keyword}'). Aborting.")
        return None

    template = load_template(article_type)
    run_id = generate_run_id()
    affiliate_id = os.getenv("PRICERUNNER_AFFILIATE_ID", "")
    partner_id = os.getenv("PRICERUNNER_PARTNER_ID", "")

    # Stage 1: Brief loop
    brief = None
    feedback = None
    for attempt in range(1, BRIEF_MAX_RETRIES + 1):
        context_str = build_brief_context(topic, keyword, products, template, "", feedback)
        brief = openclaw_phase(context_str)
        review_ctx = build_brief_review_context(brief, template)
        review = openclaw_phase(review_ctx)
        record_review_attempt(run_id, "brief", attempt, review.get("passed", False),
                               review.get("score"), review.get("feedback"))
        if review.get("passed") and review.get("score", 0) >= PASS_SCORE:
            break
        feedback = review.get("feedback")
        if attempt == BRIEF_MAX_RETRIES:
            log.error(f"Brief for '{topic}' failed after {BRIEF_MAX_RETRIES} attempts.")
            return None

    # Stage 2: Article loop
    draft = None
    feedback = None
    article_approval_score = 0.0
    for attempt in range(1, ARTICLE_MAX_RETRIES + 1):
        context_str = build_article_context(brief, products, template, COMPLIANCE_RULES, feedback)
        draft = openclaw_phase(context_str)
        review_ctx = build_article_review_context(draft, brief, template, COMPLIANCE_RULES)
        review = openclaw_phase(review_ctx)
        record_review_attempt(run_id, "article", attempt, review.get("passed", False),
                               review.get("score"), review.get("feedback"))
        if review.get("passed") and review.get("score", 0) >= PASS_SCORE:
            article_approval_score = review.get("score", 0)
            break
        feedback = review.get("feedback")
        if attempt == ARTICLE_MAX_RETRIES:
            log.error(f"Article '{topic}' failed after {ARTICLE_MAX_RETRIES} attempts.")
            return None

    # Stage 3: Optimization loop (SEO + CRO + review, max 1 retry)
    published_titles = get_published_titles(site_config.name)
    opt_issues = None
    for opt_attempt in range(1, 3):
        draft = openclaw_phase(build_seo_context(draft, keyword, [], published_titles, opt_issues))
        draft = openclaw_phase(build_cro_context(draft, template, opt_issues))
        opt_review = openclaw_phase(build_optimization_review_context(draft, article_approval_score))
        record_review_attempt(run_id, "optimization", opt_attempt,
                               opt_review.get("passed", False),
                               opt_review.get("score"), opt_review.get("feedback"))
        if opt_review.get("passed"):
            break
        if opt_attempt >= 2:
            log.error(f"Optimization review failed for '{topic}'. Flagging for human review.")
            return None
        opt_issues = opt_review.get("issues", [])

    # Stage 4: Compliance + audit
    html, _ = inject_compliance(draft.get("body_html", ""), affiliate_id, partner_id, category_id)
    audit = deterministic_audit(html)
    if not audit.passed:
        log.error(f"Deterministic audit failed: {audit.errors}")
        return None

    # Stage 5: Create WP draft
    article = Article(
        title=draft.get("title", ""),
        slug=draft.get("slug", ""),
        body_html=html,
        yoast_meta=draft.get("yoast_meta", {}),  # type: ignore
        categories=draft.get("categories", []),
        tags=draft.get("tags", []),
        featured_image_url=draft.get("featured_image_url"),
    )
    result = create_draft(article, site_config)
    record_run(run_id, site_config.name, topic, keyword, category_id, article_type,
               "success", result.post_id, result.post_url)
    log.info(f"Draft created: {result.post_url}")
    return result
