/**
 * Build a live brief for any PriceRunner category ID.
 * Usage: npx tsx scripts/build-live-brief.ts <categoryId> <categorySlug> [siteKey]
 * Example: npx tsx scripts/build-live-brief.ts 1258 boremaskiner techblog
 *
 * Bypasses config/categories.json so any category ID can be tested directly.
 * Writes: prompts/brief-<slug>-live.json
 */
import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { v4 as uuidv4 } from "uuid";

import { fetchProductsByCategoryId } from "../src/scraper/pricerunner-client.js";
import { classifyProducts } from "../src/services/article-classifier.js";
import { SITE_CONFIGS } from "../src/config/sites.js";
import type { ContentBrief, ImageRef } from "../src/types/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROMPTS_DIR = join(__dirname, "../prompts");

const categoryId = process.argv[2] ?? "1258";
const categorySlug = process.argv[3] ?? `category-${categoryId}`;
const siteKey = process.argv[4] ?? "techblog";
const country = "DK";
const topN = 5;

console.log(`\n[build-live-brief] Fetching category ${categoryId} (${categorySlug}) from PriceRunner ${country}...\n`);

const allProducts = await fetchProductsByCategoryId(categoryId, country, 30);
console.log(`  Fetched ${allProducts.length} products`);

// Sort by popularity score, take top N
const top = allProducts
  .filter((p) => !p.outOfStock)
  .sort((a, b) => b.popularityScore - a.popularityScore)
  .slice(0, topN);

console.log(`  Top ${topN} by popularity:`);
top.forEach((p, i) => {
  const rank = p.specs["popularityRank"] ?? "?";
  const watched = p.specs["watchedLabel"] ? ` 👁 ${p.specs["watchedLabel"]}` : "";
  console.log(`  ${i + 1}. #${rank} ${p.name} — ${p.priceKr} kr. (score: ${p.popularityScore})${watched}`);
});

// Classify
const classified = classifyProducts(top);
console.log(`\n  Classifier → articleType: "${classified.articleType}"`);
console.log(`  Hook: "${classified.articleHook}"`);

// Ensure the hook uses the current year
const currentYear = new Date().getFullYear().toString();
classified.articleHook = classified.articleHook.replace(/\\b20\\d{2}\\b/g, currentYear);

// Build images
const images: ImageRef[] = top.map((p) => ({
  productId: p.id,
  url: p.imageUrl,
  alt: `${p.name} — ${p.specs["brand"] ?? ""}`,
  caption: `${p.name} — ${p.priceKr.toLocaleString("da-DK")} kr. hos ${p.retailer || "sammenlign"}`,
}));

const siteConfig = SITE_CONFIGS[siteKey];

const brief: ContentBrief = {
  brief_id: uuidv4(),
  category: categorySlug,
  products: top.map(({ imageUrl: _i, popularityScore: _s, outOfStock: _o, ...rest }) => rest),
  images,
  writing_rules: {
    tone: "practical",
    minWords: 600,
    maxWords: 1200,
    includeProsCons: classified.articleType === "single-product-review",
    includeVerdict: true,
  },
  compliance: {
    requireDisclosure: true,
    disclosurePhrases: ["indeholder affiliatelinks", "vi tjener kommission", "annonce", "reklame"],
    forbiddenSuperlatives: ["bedste på markedet", "billigst i danmark", "nr. 1 valg", "absolut bedst"],
  },
  articleType: classified.articleType,
  currentDate: new Date().toISOString().split("T")[0],
    articleHook: classified.articleHook,
};

mkdirSync(PROMPTS_DIR, { recursive: true });
const briefPath = join(PROMPTS_DIR, `brief-${categorySlug}-live.json`);
const output = { job_id: uuidv4(), brief };
writeFileSync(briefPath, JSON.stringify(output, null, 2), "utf-8");

console.log(`\n✅ Brief written to ${briefPath}`);
console.log(`   ${top.length} products | type: ${classified.articleType}`);
console.log(`\nNext step:`);
console.log(`  npx tsx scripts/validate-article.ts prompts/article-${categorySlug}-live.json ${briefPath}`);
