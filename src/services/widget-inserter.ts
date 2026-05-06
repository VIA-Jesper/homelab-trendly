import type { ContentBrief } from "../types/index.js";

const PLACEHOLDER_REGEX = /\{\{AFFILIATE_WIDGET_([A-Z0-9_]+)\}\}/g;

function renderWidget(productId: string, brief: ContentBrief): string {
  const product = brief.products.find((p) => p.id === productId);
  if (!product) {
    console.warn(`[widget-inserter] Unknown product id: ${productId} — skipping`);
    return "";
  }
  return `<div class="trendly-affiliate-widget" data-product-id="${product.id}">
  <div class="taw-name">${product.name}</div>
  <div class="taw-price">${product.priceKr.toLocaleString("da-DK")} kr.</div>
  <div class="taw-retailer">Hos ${product.retailer}</div>
  <a class="taw-cta" href="${product.affiliateUrl}" rel="sponsored noopener" target="_blank">
    Se pris hos ${product.retailer}
  </a>
</div>`;
}

export function insertWidgets(article: string, brief: ContentBrief): string {
  return article.replace(PLACEHOLDER_REGEX, (_match, productId: string) =>
    renderWidget(productId, brief)
  );
}
