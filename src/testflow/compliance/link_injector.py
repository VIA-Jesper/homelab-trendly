"""
Affiliate link injector.

Scans all <a> tags pointing to pricerunner.dk and:
1. Appends ?ref-site={AFFILIATE_ID} to the href
2. Adds rel="sponsored nofollow"
3. Adds target="_blank"

Idempotent - running twice does not double-append ref param.
"""
import os
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from bs4 import BeautifulSoup
from testflow.compliance.rules import COMPLIANCE_RULES


def _add_ref_param(url: str, affiliate_id: str) -> str:
    """Add ?ref-site=affiliate_id to a URL, replacing any existing value."""
    ref_param = COMPLIANCE_RULES["affiliate_links"]["ref_param"]
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[ref_param] = [affiliate_id]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


def inject_affiliate_links(html: str, affiliate_id: str) -> str:
    """
    Add ref-site param and rel/target attrs to all PriceRunner links.
    Idempotent: safe to run multiple times.
    """
    if not affiliate_id:
        affiliate_id = os.getenv("PRICERUNNER_AFFILIATE_ID", "")

    domain = COMPLIANCE_RULES["affiliate_links"]["domain"]
    required_rel = COMPLIANCE_RULES["affiliate_links"]["required_rel"]

    soup = BeautifulSoup(html, "html.parser")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if domain not in href:
            continue

        # Add ref param
        a_tag["href"] = _add_ref_param(href, affiliate_id)

        # Set rel attribute (merge with existing, deduplicate)
        existing_rel = a_tag.get("rel", [])
        if isinstance(existing_rel, str):
            existing_rel = existing_rel.split()
        merged_rel = list(dict.fromkeys(existing_rel + required_rel))
        a_tag["rel"] = " ".join(merged_rel)

        # Set target
        a_tag["target"] = "_blank"

    return str(soup)
