"""
COMPLIANCE_RULES - single source of truth for all compliance requirements.

Imported by:
- inject_compliance.py  (to apply transforms)
- tools.py / deterministic_audit  (to check article HTML)
- prompts.py  (injected into article generation context so OpenClaw knows what to produce)
"""

COMPLIANCE_RULES = {
    "disclosure": {
        "required": True,
        "position": "top",   # must be first element in body
        "html": (
            '<div class="affiliate-disclosure">'
            "<p>Denne artikel indeholder affiliate-links. Vi kan modtage en kommission, "
            "hvis du kober via vores links - uden ekstra omkostninger for dig.</p>"
            "</div>"
        ),
        "check": "div.affiliate-disclosure must exist as first child of body",
    },
    "affiliate_links": {
        "domain": "pricerunner.dk",
        "ref_param": "ref-site",          # ?ref-site={PRICERUNNER_AFFILIATE_ID}
        "widget_param": "partnerId",      # in JS widget embed
        "required_rel": ["sponsored", "nofollow"],
        "required_target": "_blank",
        "check": (
            "every <a> pointing to pricerunner.dk must have "
            "?ref-site=, rel='sponsored nofollow', target='_blank'"
        ),
    },
    "prohibited_claims": [
        "billigste pris garanteret",
        "laveste pris",
        "garanti for",
        "vi garanterer",
        "billigst i Danmark",
        "nummer 1 i Danmark",
        "markedets bedste",
    ],
    "widget": {
        "required": True,
        "check": "body must contain <div class='pr-widget'> or <script src='partner.pricerunner.dk'>",
    },
}
