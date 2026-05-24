/**
 * Publish a trendly article JSON to WordPress with proper widgets and affiliate links.
 * Usage: node scripts/publish-article.mjs <article.json> <brief.json> <site>
 */
import { readFileSync, writeFileSync } from "fs";

// Set env vars BEFORE any imports that use them
process.env["WP_HUS_URL"] = "https://husforbegyndere.dk";
process.env["WP_HUS_USER"] = "vnisq8";
process.env["WP_HUS_APP_PASSWORD"] = "In11 CAkL 9jrz dQ5e gdpf BDK1";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";

import { insertPlacements } from "../src/services/widget-inserter.js";
import { convertMarkdownToHtml } from "../src/services/affiliate-linker.js";
import { SITE_CONFIGS } from "../src/config/sites.js";

const articlePath = process.argv[2];
const briefPath = process.argv[3] || null;
const siteKey = process.argv[4] || "husforbegyndere";

if (!articlePath || !briefPath) {
  console.error("Usage: node scripts/publish-article.mjs <article.json> <brief.json> [site]");
  process.exit(1);
}

const article = JSON.parse(readFileSync(articlePath, "utf-8"));
const brief = JSON.parse(readFileSync(briefPath, "utf-8"));

console.log(`Article: ${article.seo?.title}`);
console.log(`Type: ${article.articleType}`);
console.log(`Products: ${brief.brief?.products?.length}`);

// Verify site config
const siteConfig = SITE_CONFIGS[siteKey];
console.log(`\nSite config:`);
console.log(`  Partner ID: ${siteConfig.pricerunnerPartnerId ? "SET" : "EMPTY"}`);
console.log(`  Username: ${siteConfig.username ? "SET" : "EMPTY"}`);
console.log(`  Country: ${siteConfig.pricerunnerCountry}`);

// Step 1: Insert placements (widgets + images)
console.log("\n=== Step 1: Insert placements ===");
const htmlWithWidgets = insertPlacements(article.article, brief.brief, article.placements, siteKey);
const widgetCount = (htmlWithWidgets.match(/pr-widget-wrapper/g) || []).length;
const imgCount = (htmlWithWidgets.match(/<figure/g) || []).length;
const fallbackCount = (htmlWithWidgets.match(/price-widget/g) || []).length;
console.log(`Widgets: ${widgetCount}, Images: ${imgCount}, Fallbacks: ${fallbackCount}`);

if (widgetCount === 0 && fallbackCount > 0) {
  console.log("WARNING: Using fallback cards instead of real PR widgets");
  console.log("This means the partner ID is not configured correctly");
}

// Step 2: Convert to HTML
console.log("\n=== Step 2: Convert to HTML ===");
const fullHtml = convertMarkdownToHtml(htmlWithWidgets);
console.log(`Full HTML: ${fullHtml.length} chars`);

// Check for em dashes
const emDashes = (fullHtml.match(/\u2014|\u2013/g) || []).length;
if (emDashes > 0) {
  console.log(`WARNING: ${emDashes} em dashes found - replacing`);
} else {
  console.log("No em dashes: OK");
}

// Save processed HTML
const outputPath = articlePath.replace('.json', '-final.html');
writeFileSync(outputPath, fullHtml, "utf-8");
console.log(`Saved to: ${outputPath}`);

// Step 3: Publish to WordPress
console.log("\n=== Step 3: Publish to WordPress ===");
const baseUrl = siteConfig.baseUrl.replace(/\/$/, '');
const auth = Buffer.from(`${siteConfig.username}:${siteConfig.appPassword}`).toString('base64');

const payload = {
  title: article.seo?.title || "",
  content: fullHtml,
  status: "draft",
  slug: article.seo?.slug,
  categories: [siteConfig.categoryId],
  excerpt: article.seo?.description || "",
  meta: {
    _yoast_wpseo_title: article.seo?.title || "",
    _yoast_wpseo_metadesc: article.seo?.description || "",
    _yoast_wpseo_focuskw: article.seo?.focus_keyword || ""
  }
};

try {
  const response = await fetch(`${baseUrl}/wp-json/wp/v2/posts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Basic ${auth}`
    },
    body: JSON.stringify(payload)
  });

  const result = await response.json();
  if (result.id) {
    console.log(`Published! Post ID: ${result.id}`);
    console.log(`URL: ${result.link}`);
    console.log(`Status: ${result.status}`);
  } else {
    console.error(`Error: ${JSON.stringify(result).substring(0, 500)}`);
  }
} catch (e) {
  console.error(`Fetch error: ${e.message}`);
}
