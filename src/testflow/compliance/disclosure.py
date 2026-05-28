"""
Affiliate disclosure injector.

Inserts the Danish affiliate disclosure div as the very first element
in the article body. Idempotent - will not double-inject.
"""
from bs4 import BeautifulSoup
from testflow.compliance.rules import COMPLIANCE_RULES


def inject_disclosure(html: str) -> str:
    """
    Ensure the affiliate disclosure div is the first element in the article.
    If a disclosure div already exists, it is left in place (idempotent).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check if disclosure already present
    existing = soup.find("div", class_="affiliate-disclosure")
    if existing:
        return str(soup)

    # Find the body element or root of content
    body = soup.find("article") or soup.find("body") or soup

    # Parse the disclosure HTML fragment
    disclosure_html = COMPLIANCE_RULES["disclosure"]["html"]
    disclosure_soup = BeautifulSoup(disclosure_html, "html.parser")
    disclosure_div = disclosure_soup.find("div", class_="affiliate-disclosure")

    if disclosure_div and body:
        # Insert as first child
        if body.contents:
            body.contents[0].insert_before(disclosure_div)
        else:
            body.append(disclosure_div)

    return str(soup)
