"""
PriceRunner widget injector.

Ensures the PriceRunner JS widget embed is present in the article.
The widget is a <div class="pr-widget"> placeholder + a <script> tag.

If neither is found, injects the widget after the first <p> tag (intro paragraph).
Idempotent - if widget already present, leaves it in place.
"""
import os
from bs4 import BeautifulSoup


def inject_widget(html: str, category_id: int, partner_id: str = "") -> str:
    """
    Ensure the PriceRunner widget block is present in the article.

    Args:
        html: Raw article HTML
        category_id: PriceRunner numeric category ID for the widget
        partner_id: PriceRunner partner ID (from PRICERUNNER_PARTNER_ID env var if not passed)

    Returns:
        HTML with widget guaranteed to be present.
    """
    if not partner_id:
        partner_id = os.getenv("PRICERUNNER_PARTNER_ID", "")

    soup = BeautifulSoup(html, "html.parser")

    # Check if widget already present
    existing_widget = soup.find("div", class_="pr-widget")
    existing_script = soup.find("script", src=lambda s: s and "partner.pricerunner.dk" in s)
    if existing_widget or existing_script:
        return str(soup)

    # Build widget HTML
    widget_div = soup.new_tag("div", attrs={"class": "pr-widget", "data-category-id": str(category_id)})
    script_tag = soup.new_tag(
        "script",
        src=(
            f"https://partner.pricerunner.dk/api/widget/v2/category/{category_id}"
            f"?partnerId={partner_id}&locale=da-DK"
        ),
    )
    script_tag["async"] = ""

    # Find insertion point: after the first <p> inside the article/body
    body = soup.find("article") or soup.find("body") or soup
    first_p = body.find("p")

    if first_p:
        first_p.insert_after(script_tag)
        first_p.insert_after(widget_div)
    else:
        # No <p> found - append at end
        if body:
            body.append(widget_div)
            body.append(script_tag)

    return str(soup)
