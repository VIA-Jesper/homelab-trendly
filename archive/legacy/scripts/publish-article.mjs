/**
 * Publish a trendly article JSON to WordPress.
 * Uses the same publishToWordPress service as the MCP tool - widgets, affiliate links,
 * partner ID stamping, and SEO meta are all handled identically.
 *
 * Usage: node scripts/publish-article.mjs <article.json> <brief.json> [site] [--draft]
 * Example: node scripts/publish-article.mjs prompts/article-robotstovsugere-live.json prompts/brief-robotstovsugere-live.json husforbegyndere
 */
import { readFileSync } from "fs";
import { config } from "dotenv";

config(); // load .env

import { publishToWordPress } from "../src/services/wp-publisher.js";

const articlePath = process.argv[2];
const briefPath = process.argv[3];
const siteKey = process.argv[4] || "husforbegyndere";
const asDraft = process.argv.includes("--draft");

if (!articlePath || !briefPath) {
  console.error("Usage: node scripts/publish-article.mjs <article.json> <brief.json> [site] [--draft]");
  process.exit(1);
}

const article = JSON.parse(readFileSync(articlePath, "utf-8"));
const briefWrapper = JSON.parse(readFileSync(briefPath, "utf-8"));
const brief = briefWrapper.brief ?? briefWrapper;

console.log(`Article : ${article.seo?.title}`);
console.log(`Type    : ${article.articleType}`);
console.log(`Products: ${brief.products?.length}`);
console.log(`Site    : ${siteKey}`);
console.log(`Status  : ${asDraft ? "draft" : "publish"}`);
console.log();

const result = await publishToWordPress({
  jobId: article.job_id ?? "manual",
  article: article.article,
  brief,
  siteKey,
  status: asDraft ? "draft" : "publish",
  placements: article.placements ?? [],
  seo: article.seo,
});

console.log(`\nDone: ${result.status}`);
console.log(`URL : ${result.url}`);
if (result.warnings?.length) {
  console.log(`\nWarnings:`);
  result.warnings.forEach((w) => console.log(`  - ${w}`));
}
