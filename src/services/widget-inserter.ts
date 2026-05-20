import { randomUUID } from "crypto";
import type { ContentBrief, Placement } from "../types/index.js";
import { SITE_CONFIGS } from "../config/sites.js";

type WidgetVariant = "singleproduct" | "product";

/** Strip "pr_" prefix → numeric PriceRunner product ID */
function numericId(productId: string): string {
  return productId.replace(/^pr_/, "");
}

// ─── Image HTML ───────────────────────────────────────────────────────────────
function renderImage(
  productId: string,
  brief: ContentBrief
): string {
  const product = brief.products.find((p) => p.id === productId);
  const image = brief.images.find((img) => img.productId === productId);
  if (!product || !image?.url) return "";

  const brand = product.specs["brand"];
  const alt = brand ? `${product.name} - ${brand}` : product.name;

  return `\n\n<figure class="my-8">
  <img src="${image.url}" alt="${alt}" loading="lazy" class="mx-auto rounded-xl shadow-md border border-gray-100" />
  <figcaption class="text-center text-sm text-gray-500 mt-3 font-medium">${image.caption}</figcaption>
</figure>\n\n`;
}

// ─── Widget HTML ──────────────────────────────────────────────────────────────

/**
 * Renders the actual PriceRunner JS embed widget.
 *  - "singleproduct" → singleproduct.js  (lowest price, best for hero/SPR star product)
 *  - "product"       → product.js         (up to 3 offers, best for alternatives/roundups)
 * Falls back to a styled Tailwind card when partnerId is not configured.
 */
function renderWidget(
  productId: string,
  brief: ContentBrief,
  siteKey: string,
  variant: WidgetVariant
): string {
  const product = brief.products.find((p) => p.id === productId);
  if (!product) {
    console.warn(`[widget-inserter] Unknown product id: ${productId} — skipping`);
    return "";
  }

  const siteConfig = SITE_CONFIGS[siteKey];
  const partnerId = siteConfig?.pricerunnerPartnerId ?? "";
  const country = (siteConfig?.pricerunnerCountry ?? "DK").toLowerCase();

  if (!partnerId) {
    return renderTailwindFallback(product);
  }

  const pid = numericId(product.id);
  const encodedPartnerId = encodeURIComponent(partnerId);
  const widgetElemId = `pr-${variant}-widget-${randomUUID().slice(0, 8)}`;
  const scriptFile = variant === "product" ? "product.js" : "singleproduct.js";
  const extraParams = variant === "product"
    ? "&onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3"
    : "";

  const sep = product.affiliateUrl.includes("?") ? "&" : "?";
  const productUrlWithPartner = `${product.affiliateUrl}${sep}partnerId=${encodedPartnerId}`;

  return `\n\n<div class="pr-widget-wrapper my-8">
<div id="${widgetElemId}" style="display: block; width: 100%"></div>
<script type="text/javascript" src="https://api.pricerunner.com/publisher-widgets/${country}/${scriptFile}?productId=${pid}&partnerId=${encodedPartnerId}&widgetId=${widgetElemId}${extraParams}" async></script>
<div style="display: inline-block; margin-top: 4px;">
  <a href="${productUrlWithPartner}" rel="sponsored nofollow">
    <p style="font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic; color: #888; text-decoration: underline; margin: 0;">Annonce i samarbejde med <span style="font-weight: bold">PriceRunner</span></p>
  </a>
</div>
</div>\n\n`;
}

/** Fallback card used during local dev when PR_*_PARTNER_ID env var is not set */
function renderTailwindFallback(
  product: ContentBrief["products"][number]
): string {
  return `\n\n<div class="price-widget not-prose flex flex-col md:flex-row items-center justify-between p-6 bg-white border border-gray-200 rounded-2xl shadow-sm my-8 hover:shadow-md transition-shadow gap-6">
  <div class="flex flex-col">
    <span class="text-gray-400 text-xs uppercase tracking-widest font-bold mb-1">Prissammenligning</span>
    <h3 class="text-xl font-bold text-gray-900">${product.name}</h3>
    <div class="flex items-center gap-2 mt-2">
      <span class="text-sm font-medium text-gray-600">${product.retailer}</span>
      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">På lager</span>
    </div>
  </div>
  <div class="flex items-center gap-6">
    <div class="text-right">
      <div class="text-gray-500 text-sm mb-0.5">Fra</div>
      <div class="text-3xl font-black text-orange-600 tracking-tighter">${product.priceKr} kr.</div>
    </div>
    <a href="${product.affiliateUrl}" rel="sponsored" class="buy-btn inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white px-6 py-3 rounded-xl font-bold text-base transition-all shadow-md shadow-orange-100 whitespace-nowrap">
      Sammenlign priser &rarr;
    </a>
  </div>
</div>\n\n`;
}

// ─── Agent-directed placement engine ─────────────────────────────────────────
/**
 * Injects agent-specified image and widget HTML blocks into a Markdown article.
 * Placements are applied in descending after_paragraph order to preserve earlier indices.
 *
 * Widget variants alternate by article position:
 *   - 1st widget in article → "singleproduct" (lowest price, strong CTA)
 *   - 2nd widget in article → "product" (top 3 offers, good for alternatives)
 *   - 3rd widget → "singleproduct", etc.
 */
export function insertPlacements(
  article: string,
  brief: ContentBrief,
  placements: Placement[],
  siteKey: string
): string {
  const paragraphs = article.split(/\r?\n\s*\r?\n/);

  // Sort descending so earlier paragraph indices remain valid after each insertion
  const sorted = [...placements].sort((a, b) => b.after_paragraph - a.after_paragraph);

  // Pre-assign widget variants in article order (ascending paragraph).
  // We process descending, so widgetIdx starts at (total-1) and counts down.
  // Index 0 (first in article) → "singleproduct"; index 1 → "product"; alternating.
  const totalWidgets = placements.filter((p) => p.type === "widget").length;
  let widgetIdx = totalWidgets - 1;

  for (const placement of sorted) {
    let html: string;

    if (placement.type === "image") {
      html = renderImage(placement.productId, brief);
    } else {
      const variant: WidgetVariant = widgetIdx % 2 === 0 ? "singleproduct" : "product";
      html = renderWidget(placement.productId, brief, siteKey, variant);
      widgetIdx--;
    }

    if (!html) continue;

    const insertAt = Math.min(placement.after_paragraph, paragraphs.length);
    paragraphs.splice(insertAt, 0, html);
  }

  return paragraphs.join("\n\n");
}

// ─── Legacy sync export (kept for backward compat with test/route code) ───────
export function insertWidgets(article: string, brief: ContentBrief): string {
  return insertPlacements(article, brief, [], "techblog");
}
