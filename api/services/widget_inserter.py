"""
Widget inserter — injects PriceRunner JS widgets and product images into
article markdown at generator-specified anchor positions.

Runs at publish time and in preview — NOT as a pipeline step.
Widget HTML is derived from live brief data; if the widget format changes,
re-publishing regenerates it without re-running Claude.

Widget selection (archive/docs/pricerunner-widgets.md):
  single-product-review → product.js (3 stores, in-stock, national)
  all other article types → singleproduct.js (lowest price, compact)

Placement format from generator JSON output:
  { "type": "image"|"widget", "productId": "<id>",
    "anchor": { "kind": "after-heading"|"end-of-section"|"after-intro"|"before-heading",
                "section": "<H2 text>" } }
"""

import re
import uuid
from urllib.parse import quote

from services.brief_builder import ContentBrief, ImageRef, ProductBrief, get_site_config


def _widget_id() -> str:
    return uuid.uuid4().hex[:8]


def _numeric_id(product_id: str) -> str:
    """Strip 'pr_' prefix to get the raw numeric PriceRunner product ID."""
    return product_id.removeprefix("pr_")


def _slugify(text: str) -> str:
    for src, dst in [("æ", "ae"), ("ø", "oe"), ("å", "aa")]:
        text = text.replace(src, dst)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def render_widget(product: ProductBrief, partner_id: str, article_type: str) -> str:
    """
    PriceRunner JS embed for one product.
    single-product-review → product.js (3 stores); everything else → singleproduct.js.
    """
    pid = _numeric_id(product.id)
    wid = _widget_id()
    encoded_partner = quote(partner_id)

    if article_type == "single-product-review":
        elem_id = f"pr-product-widget-{wid}"
        src = (
            f"https://api.pricerunner.com/publisher-widgets/dk/product.js"
            f"?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3"
            f"&productId={pid}&partnerId={encoded_partner}&widgetId={elem_id}"
        )
    else:
        elem_id = f"pr-singleproduct-widget-{wid}"
        src = (
            f"https://api.pricerunner.com/publisher-widgets/dk/singleproduct.js"
            f"?productId={pid}&partnerId={encoded_partner}&widgetId={elem_id}"
        )

    # Attribution href: product URL without refsite so the disclosure link is clean
    disclosure_url = re.sub(r"[?&]refsite=[^&]*", "", product.affiliate_url).rstrip("?&")

    disclosure = (
        '<div style="display:inline-block">'
        f'<a href="{disclosure_url}" rel="nofollow">'
        "<p style=\"font:14px 'Klarna Text',Helvetica,sans-serif;font-style:italic;"
        'color:var(--grayscale100);text-decoration:underline;">'
        'Annonce i samarbejde med <span style="font-weight:bold">PriceRunner</span>'
        "</p></a></div>"
    )

    return (
        f'<div id="{elem_id}" style="display:block;width:100%"></div>\n'
        f'<script type="text/javascript" src="{src}" async></script>\n'
        f"{disclosure}"
    )


def render_image(image: ImageRef) -> str:
    return (
        '<figure style="margin:1.5em 0;text-align:center">'
        f'<img src="{image.url}" alt="{image.alt}" '
        'style="max-width:100%;height:auto;border-radius:4px">'
        f'<figcaption style="font-size:0.85em;color:#666;margin-top:0.4em">'
        f"{image.caption}</figcaption>"
        "</figure>"
    )


def _find_heading(lines: list[str], section: str) -> int | None:
    """Find the H1-H3 line matching section text. Tries exact, then slug, then prefix."""
    slug = _slugify(section)
    for i, line in enumerate(lines):
        m = re.match(r"^#{1,3}\s+(.+)", line)
        if not m:
            continue
        text = m.group(1).strip()
        if text == section:
            return i
        text_slug = _slugify(text)
        if text_slug == slug or text_slug.startswith(slug):
            return i
    return None


def _find_section_end(lines: list[str], heading_idx: int) -> int:
    """Line index to insert at end of section: just before next H1/H2, or EOF."""
    for i in range(heading_idx + 1, len(lines)):
        if re.match(r"^#{1,2}\s+", lines[i]):
            j = i - 1
            while j > heading_idx and not lines[j].strip():
                j -= 1
            return j + 1
    return len(lines)


def _find_after_intro(lines: list[str]) -> int | None:
    """Return insertion index after the first paragraph following the H1."""
    past_h1 = False
    in_para = False
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            past_h1 = True
            continue
        if not past_h1:
            continue
        if line.strip():
            in_para = True
        elif in_para:
            return i + 1
    return None


def insert_anchored_placements(
    article: str,
    brief: ContentBrief,
    placements: list[dict],
) -> tuple[str, list[str]]:
    """
    Insert widget and image HTML at anchor positions in the article markdown.
    Returns (modified_article, errors). Errors are non-fatal — the article is
    returned with whatever insertions succeeded.
    """
    if not placements:
        return article, []

    site_cfg = get_site_config(brief.site_key)
    partner_id = site_cfg.pricerunner_partner_id
    products_by_id: dict[str, ProductBrief] = {p.id: p for p in brief.products}
    images_by_id: dict[str, ImageRef] = {img.product_id: img for img in brief.images}

    lines = article.split("\n")
    errors: list[str] = []
    # (line_index, html_block) — applied in descending order to preserve indices
    insertions: list[tuple[int, str]] = []

    for placement in placements:
        p_type = placement.get("type", "widget")
        product_id = placement.get("productId", "")
        anchor = placement.get("anchor", {})
        kind = anchor.get("kind", "after-heading")
        section = anchor.get("section", "")

        product = products_by_id.get(product_id) or (brief.products[0] if brief.products else None)
        if not product:
            errors.append(f"No product found for productId='{product_id}'")
            continue

        if p_type == "image":
            image = images_by_id.get(product_id) or (brief.images[0] if brief.images else None)
            if not image:
                errors.append(f"No image found for productId='{product_id}'")
                continue
            html_block = render_image(image)
        else:
            html_block = render_widget(product, partner_id, brief.article_type)

        if kind == "after-intro":
            idx = _find_after_intro(lines)
            if idx is None:
                errors.append("Could not locate intro paragraph for after-intro placement")
                continue
            insertions.append((idx, html_block))
        elif kind in ("after-heading", "end-of-section", "before-heading"):
            if not section:
                errors.append(f"Missing section text for kind='{kind}'")
                continue
            h_idx = _find_heading(lines, section)
            if h_idx is None:
                errors.append(f"Heading not found: '{section}'")
                continue
            if kind == "after-heading":
                insertions.append((h_idx + 1, html_block))
            elif kind == "before-heading":
                insertions.append((h_idx, html_block))
            else:  # end-of-section
                insertions.append((_find_section_end(lines, h_idx), html_block))
        else:
            errors.append(f"Unknown anchor kind: '{kind}'")

    # Apply insertions in reverse order so earlier indices stay valid
    insertions.sort(key=lambda x: x[0], reverse=True)
    for idx, html_block in insertions:
        lines.insert(idx, "")
        lines.insert(idx + 1, html_block)
        lines.insert(idx + 2, "")

    return "\n".join(lines), errors
