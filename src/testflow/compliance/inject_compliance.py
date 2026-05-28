"""
inject_compliance - Runs all deterministic compliance transforms in order:
  1. Link injection (ref-site param + rel/target attrs)
  2. Disclosure (affiliate disclosure div at top)
  3. Widget (PriceRunner widget block)

Called AFTER OpenClaw approves the article. Not a gate - a transformer.
Idempotent: safe to run multiple times on the same HTML.
"""
import os
from testflow.compliance.link_injector import inject_affiliate_links
from testflow.compliance.disclosure import inject_disclosure
from testflow.compliance.widget_injector import inject_widget


def inject_compliance(
    html: str,
    affiliate_id: str = "",
    partner_id: str = "",
    category_id: int = 0,
) -> tuple[str, int]:
    """
    Run all compliance transforms on article HTML.

    Args:
        html: Raw article HTML from OpenClaw
        affiliate_id: PriceRunner ref-site ID (from env if not passed)
        partner_id: PriceRunner widget partner ID (from env if not passed)
        category_id: PriceRunner category ID for widget (0 = skip widget injection)

    Returns:
        Tuple of (transformed_html, transforms_applied_count)
    """
    if not affiliate_id:
        affiliate_id = os.getenv("PRICERUNNER_AFFILIATE_ID", "")
    if not partner_id:
        partner_id = os.getenv("PRICERUNNER_PARTNER_ID", "")

    transforms = 0
    original = html

    # 1. Inject ref-site params + rel/target on all PriceRunner links
    html = inject_affiliate_links(html, affiliate_id)
    if html != original:
        transforms += 1

    # 2. Inject disclosure div at top
    prev = html
    html = inject_disclosure(html)
    if html != prev:
        transforms += 1

    # 3. Inject widget (only if category_id provided)
    if category_id:
        prev = html
        html = inject_widget(html, category_id, partner_id)
        if html != prev:
            transforms += 1

    return html, transforms
