"""
Context string builders for each OpenClaw reasoning phase.

Each function returns a structured string that OpenClaw reads to understand
its task for that phase. OpenClaw produces the output using its own reasoning.

These are used by pipeline.py (CLI reference) and define what each phase should contain.
When OpenClaw drives the pipeline itself, it builds context from the skill document.
"""
import json
from testflow.models import PRProduct
from testflow.compliance.rules import COMPLIANCE_RULES
from testflow.orchestration.templates import ArticleTemplate


def _product_list_json(products: list[PRProduct]) -> str:
    return json.dumps([
        {
            "name": p.name,
            "price_min": p.price_min,
            "price_display": p.price_display,
            "affiliate_url": p.affiliate_url,
            "image_url": p.image_url,
            "rating": p.rating,
            "review_count": p.review_count,
            "merchant_count": p.merchant_count,
        }
        for p in products
    ], ensure_ascii=False, indent=2)


def build_brief_context(
    topic: str,
    keyword: str,
    products: list[PRProduct],
    template: ArticleTemplate,
    site_rules: str = "",
    feedback: str | None = None,
) -> str:
    return f"""TASK: Create a content brief for an affiliate article
TOPIC: {topic}
KEYWORD: {keyword}
ARTICLE TYPE: {template.type}
TONE: {template.tone_guidance}
PRODUCTS AVAILABLE:
{_product_list_json(products)}
SITE RULES: {site_rules or "none"}
PREVIOUS FEEDBACK: {feedback or "none"}

Return ONLY valid JSON:
{{
  "angle": "unique editorial angle for this article",
  "tone": "friendly/expert/neutral",
  "products_to_feature": ["product_name", ...],
  "outline": [
    {{ "section": "Intro", "purpose": "...", "target_words": 150 }},
    ...
  ],
  "key_claims": ["concrete claim 1", ...],
  "seo_title": "max 60 chars",
  "meta_description": "max 155 chars",
  "focus_keyword": "primary keyword"
}}"""


def build_brief_review_context(brief: dict, template: ArticleTemplate) -> str:
    required_sections = [s.id for s in template.required_sections]
    return f"""TASK: Review this content brief
BRIEF: {json.dumps(brief, ensure_ascii=False, indent=2)}
CRITERIA:
  - Angle is distinctive, not generic
  - Outline covers all required sections for article type: {required_sections}
  - Key claims are specific and verifiable (no vague superlatives)
  - Product selection is relevant to the keyword
  - SEO title max 60 chars, meta description max 155 chars

Return ONLY valid JSON: {{"passed": bool, "score": 0-10, "feedback": "...", "issues": []}}"""


def build_article_context(
    brief: dict,
    products: list[PRProduct],
    template: ArticleTemplate,
    compliance_rules: dict,
    feedback: str | None = None,
) -> str:
    return f"""TASK: Write an affiliate article from this approved brief
APPROVED BRIEF: {json.dumps(brief, ensure_ascii=False, indent=2)}
ARTICLE TEMPLATE: {template.model_dump_json(indent=2)}
PRODUCTS:
{_product_list_json(products)}
COMPLIANCE RULES: {json.dumps(compliance_rules, ensure_ascii=False, indent=2)}
PREVIOUS FEEDBACK: {feedback or "none"}

Return ONLY valid JSON matching ArticleDraft schema. No markdown fences."""


def build_article_review_context(
    draft: dict, brief: dict, template: ArticleTemplate, compliance_rules: dict
) -> str:
    return f"""TASK: Review this affiliate article draft
DRAFT: {json.dumps(draft, ensure_ascii=False, indent=2)}
APPROVED BRIEF: {json.dumps(brief, ensure_ascii=False, indent=2)}
TEMPLATE REQUIRED SECTIONS: {[s.id for s in template.required_sections]}
COMPLIANCE RULES: {json.dumps(compliance_rules, ensure_ascii=False, indent=2)}

Return ONLY valid JSON:
{{"passed": bool, "score": 0-10, "feedback": "...",
  "issues": [{{"type": "...", "severity": "blocker|quality", "fix": "..."}}]}}"""


def build_seo_context(
    draft: dict,
    keyword: str,
    related_keywords: list[str],
    published_titles: list[str],
    issues: list | None = None,
) -> str:
    return f"""TASK: Optimise this article for search
DRAFT: {json.dumps(draft, ensure_ascii=False, indent=2)}
PRIMARY KEYWORD: {keyword}
SECONDARY KEYWORDS: {related_keywords}
EXISTING ARTICLES (for internal linking): {published_titles[:20]}
ISSUES TO FIX: {issues or "none"}

Return updated ArticleDraft JSON with SEO improvements applied."""


def build_cro_context(
    draft: dict, template: ArticleTemplate, issues: list | None = None
) -> str:
    return f"""TASK: Optimise this article for conversion
DRAFT: {json.dumps(draft, ensure_ascii=False, indent=2)}
ARTICLE TYPE: {template.type}
ISSUES TO FIX: {issues or "none"}

Return updated ArticleDraft JSON with CRO improvements applied."""


def build_optimization_review_context(draft: dict, original_approval_score: float) -> str:
    return f"""TASK: Review this article after SEO and CRO optimisation
DRAFT: {json.dumps(draft, ensure_ascii=False, indent=2)}
ORIGINAL APPROVAL SCORE: {original_approval_score}

Check that optimisation did NOT introduce keyword stuffing, broken compliance,
or loss of quality. Return ONLY valid JSON:
{{"passed": bool, "score": 0-10, "feedback": "...",
  "issues": [{{"type": "...", "severity": "blocker|warning", "fix": "..."}}]}}"""
