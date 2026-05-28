"""
Tests for the affiliate compliance engine.

Tests inject_compliance() and deterministic_audit() in isolation.
Input: raw HTML. Output: transformed HTML + audit result.
No HTTP calls - fully deterministic.
"""
import pytest
from testflow.compliance.inject_compliance import inject_compliance
from testflow.compliance.rules import COMPLIANCE_RULES
from testflow.orchestration.tools import deterministic_audit

# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_ARTICLE = """
<article>
  <h1>Bedste Robotstovsuger</h1>
  <p>Se de bedste modeller pa <a href="https://www.pricerunner.dk/cl/1613/Robotstovsuger">PriceRunner</a>.</p>
  <p>Kob Roomba j9+ hos <a href="https://www.pricerunner.dk/pl/1234/Roomba">PriceRunner</a>.</p>
</article>
"""

# ── inject_compliance tests ───────────────────────────────────────────────────

def test_disclosure_injected():
    html, _ = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    assert 'class="affiliate-disclosure"' in html


def test_disclosure_appears_before_h1():
    html, _ = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    assert html.index("affiliate-disclosure") < html.index("<h1>")


def test_ref_param_added_to_pricerunner_links():
    html, _ = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    assert "ref-site=TEST123" in html


def test_all_pricerunner_links_have_ref_param():
    html, _ = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    pr_links = [a for a in soup.find_all("a") if "pricerunner.dk" in a.get("href", "")]
    assert pr_links, "No pricerunner.dk links found"
    assert all("ref-site=TEST123" in a["href"] for a in pr_links)


def test_links_get_sponsored_nofollow():
    html, _ = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    pr_links = [a for a in soup.find_all("a") if "pricerunner.dk" in a.get("href", "")]
    for link in pr_links:
        rel = link.get("rel", [])
        if isinstance(rel, str):
            rel = rel.split()
        assert "sponsored" in rel
        assert "nofollow" in rel


def test_idempotent_double_inject():
    """Running inject_compliance twice must not double-inject disclosure or ref params."""
    html1, _ = inject_compliance(MINIMAL_ARTICLE, "TEST123", "PART456")
    html2, _ = inject_compliance(html1, "TEST123", "PART456")
    assert html2.count("affiliate-disclosure") == 1
    assert html2.count("ref-site=TEST123") == html1.count("ref-site=TEST123")


# ── deterministic_audit tests ─────────────────────────────────────────────────

def test_audit_passes_after_inject():
    html, _ = inject_compliance(MINIMAL_ARTICLE, "TEST123", "PART456")
    report = deterministic_audit(html)
    assert report.passed, f"Audit failed: {report.errors}"


def test_audit_fails_without_disclosure():
    html = "<article><p>Se <a href='https://www.pricerunner.dk/pl/1?ref-site=X' rel='sponsored nofollow'>produkt</a>.</p></article>"
    report = deterministic_audit(html)
    assert not report.passed
    assert any("disclosure" in e.lower() for e in report.errors)


def test_audit_fails_without_ref_param():
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <a href="https://www.pricerunner.dk/pl/1234">link without ref</a>
    </article>"""
    report = deterministic_audit(html)
    assert not report.passed
    assert any("ref-site" in e for e in report.errors)


def test_audit_flags_prohibited_claim():
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <p>Dette er billigste pris garanteret <a href="https://www.pricerunner.dk/pl/1?ref-site=X" rel="sponsored nofollow">link</a>.</p>
    </article>"""
    report = deterministic_audit(html)
    assert not report.passed
    assert any("billigste pris garanteret" in e for e in report.errors)
