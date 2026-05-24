import { readFileSync } from "fs";
import { insertPlacements } from "../src/services/widget-inserter.js";
import { SITE_CONFIGS } from "../src/config/sites.js";

process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";

const article = JSON.parse(readFileSync("/tmp/single-product-article.json", "utf-8"));
const brief = JSON.parse(readFileSync("/tmp/brief-single-product.json", "utf-8"));

console.log("=== Site Config ===");
const hus = SITE_CONFIGS["husforbegyndere"];
console.log("Partner ID:", JSON.stringify(hus.pricerunnerPartnerId));
console.log("Country:", hus.pricerunnerCountry);
console.log("Username:", hus.username);

console.log("\n=== Brief Products ===");
for (const p of brief.brief.products) {
  console.log(`  ${p.id}: ${p.name}`);
  console.log(`  affiliateUrl: ${p.affiliateUrl?.substring(0, 80)}`);
}

console.log("\n=== Placements ===");
for (const pl of article.placements) {
  console.log(`  ${pl.type}: productId=${pl.productId}, after_para=${pl.after_paragraph}`);
}

console.log("\n=== Insert Placements ===");
const result = insertPlacements(article.article, brief.brief, article.placements, "husforbegyndere");

const widgetCount = (result.match(/pr-widget-wrapper/g) || []).length;
const imgCount = (result.match(/<figure/g) || []).length;
const fallbackCount = (result.match(/price-widget/g) || []).length;
console.log(`Widgets: ${widgetCount}`);
console.log(`Images: ${imgCount}`);
console.log(`Fallback cards: ${fallbackCount}`);
console.log(`Has partnerId: ${result.includes("partnerId")}`);
console.log(`Has PR script: ${result.includes("pricerunner.com/publisher-widgets")}`);

// Show a snippet around where widget should be
const widgetIdx = result.indexOf("pr-widget-wrapper");
if (widgetIdx >= 0) {
  console.log(`\nWidget snippet: ${result.substring(widgetIdx, widgetIdx + 300)}`);
} else {
  console.log("\nNo widget found in output");
  // Show what's at the widget placement point
  const paragraphs = result.split(/\n\n/);
  console.log(`\nParagraph count: ${paragraphs.length}`);
  // Check placement after_paragraph 3
  if (paragraphs[3]) {
    console.log(`Para 3: ${paragraphs[3].substring(0, 200)}`);
  }
}
