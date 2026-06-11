/**
 * Validate a generated article JSON against content rules, then dry-run
 * the full pipeline (placements → markdown→HTML → affiliate linking).
 *
 * Usage:
 *   npx tsx scripts/validate-article.ts [article-json-file] [brief-json-file]
 *
 * Defaults:
 *   article: prompts/article-laptops-sample.json
 *   brief:   prompts/brief-laptops-sample.json
 */

import { readFileSync, writeFileSync } from "fs";
import { resolve } from "path";
import { insertPlacements } from "../src/services/widget-inserter.js";
import { convertMarkdownToHtml, extractH1, insertAffiliateLinks } from "../src/services/affiliate-linker.js";
import { getTypeRules } from "../src/services/article-type-config.js";
import type { ContentBrief, Placement } from "../src/types/index.js";

// ── Load files ────────────────────────────────────────────────────────────────
const articleFile = process.argv[2] ?? "prompts/article-laptops-sample.json";
const briefFile   = process.argv[3] ?? "prompts/brief-laptops-sample.json";

function loadArticle(path: string) {
  const raw = readFileSync(resolve(path), "utf-8");
  try {
    return JSON.parse(raw);
  } catch (err) {
    // Attempt to fix raw newlines in the "article" field which break JSON syntax
    // This happens when AI output is saved literally without JSON escaping.
    const fixed = raw.replace(/"article":\s*"([\s\S]*?)",\s*"placements"/, (match, content) => {
      const escaped = content
        .replace(/\n/g, "\\n")
        .replace(/\r/g, "\\r")
        .replace(/\t/g, "\\t");
      return `"article": "${escaped}", "placements"`;
    });
    return JSON.parse(fixed);
  }
}

const articleData = loadArticle(articleFile) as {
  job_id: string;
  site: string;
  articleType?: string;
  status: string;
  article: string;
  placements: Placement[];
  seo: {
    title: string;
    description: string;
    slug: string;
    focus_keyword: string;
    featured_image_product_id: string;
  };
};
const briefData = JSON.parse(readFileSync(resolve(briefFile), "utf-8")) as {
  brief: ContentBrief;
};

const article    = articleData.article;
const brief      = briefData.brief;
const placements = articleData.placements;
const siteKey    = articleData.site;

// Resolve article type: article JSON wins, then brief, then default "roundup"
const resolvedType = articleData.articleType ?? brief.articleType ?? "roundup";
const typeRules = getTypeRules(resolvedType);

console.log(`\n  ℹ️  Article type: "${typeRules.articleType}" (from ${articleData.articleType ? "article JSON" : brief.articleType ? "brief" : "default"})`);


// ── Helpers ───────────────────────────────────────────────────────────────────
function pass(label: string, msg = "") { console.log(`  ✅ ${label}${msg ? " - " + msg : ""}`); }
function fail(label: string, msg = "") { console.log(`  ❌ ${label}${msg ? " - " + msg : ""}`); }
function warn(label: string, msg = "") { console.log(`  ⚠️  ${label}${msg ? " - " + msg : ""}`); }
function section(title: string)        { console.log(`\n${"─".repeat(60)}\n  ${title}\n${"─".repeat(60)}`); }

let failures = 0;

// ── 1. Content checks ─────────────────────────────────────────────────────────
section("1. Content compliance");

// Word count - use type-aware targets
const wordCount = article.trim().split(/\s+/).length;
const { minWords, maxWords } = typeRules;
if (wordCount < minWords) { fail("Word count", `${wordCount} words - below minimum of ${minWords} for type "${typeRules.articleType}"`); failures++; }
else if (wordCount > maxWords) { warn("Word count", `${wordCount} words - above recommended maximum of ${maxWords} for type "${typeRules.articleType}"`); }
else { pass("Word count", `${wordCount} words (${minWords}-${maxWords} for "${typeRules.articleType}")`); }

// Disclosure (optional - handled by WordPress site-wide banner)
const articleLower = article.toLowerCase();
const disclosureFound = brief.compliance.disclosurePhrases.some(p => articleLower.includes(p.toLowerCase()));
if (disclosureFound) pass("Disclosure phrase present (in-article)");
else { warn("Disclosure phrase", "Not found in article body - ensure WordPress site-wide disclosure is active"); }

// Forbidden superlatives
for (const term of brief.compliance.forbiddenSuperlatives) {
  if (articleLower.includes(term.toLowerCase())) { fail("Forbidden term found", `"${term}"`); failures++; }
}
if (!brief.compliance.forbiddenSuperlatives.some(t => articleLower.includes(t.toLowerCase()))) {
  pass("No forbidden superlatives");
}

// Pros/Cons - only required for types that specify it
// Accept both traditional headers (fordele/ulemper) and type-module variants (det vi kan lide / det vi ville ændre)
if (typeRules.requireProsCons) {
  const hasProsCons = /fordele|ulemper|det vi kan lide|det vi ville \u00e6ndre/i.test(article);
  if (hasProsCons) pass("Pros/Cons sections present");
  else { fail("Pros/Cons sections MISSING (required for type: " + typeRules.articleType + ")"); failures++; }
} else {
  pass("Pros/Cons", `not required for type "${typeRules.articleType}"`);
}

// Verdict - all types currently require a verdict
if (typeRules.requireVerdict) {
  const hasVerdict = /vores dom|konklusion|sammenfattende|sådan vælger du|det ender med|hvilken skal du vælge/i.test(article);
  if (hasVerdict) pass("Verdict section present");
  else { fail("Verdict section MISSING"); failures++; }
}

// All products covered
for (const product of brief.products) {
  // Check for a rough name match (first ~30 chars of product name)
  const shortName = product.name.slice(0, 30).toLowerCase();
  if (articleLower.includes(shortName)) pass(`Product covered: ${product.id}`);
  else { warn(`Product may be missing: ${product.id} ("${product.name.slice(0, 40)}...")`); }
}

// ── 2. Placements sanity ──────────────────────────────────────────────────────
section("2. Placement sanity");

// Split on double newline (Markdown paragraph boundary)
// Handle both \n\n and \r\n\r\n
const paragraphs = article.split(/\r?\n\s*\r?\n/);
const paraCount  = paragraphs.length;
console.log(`     Article has ${paraCount} paragraph blocks`);

let badPlacements = 0;
for (const p of placements) {
  if (p.after_paragraph > paraCount) {
    warn(`Placement out of range`, `${p.type} for ${p.productId} at paragraph ${p.after_paragraph} (max: ${paraCount})`);
    badPlacements++;
  }
}
// Check placements per product - rules vary by article type:
// - hero: hero product (first/rank-1) needs image+widget; alternatives need widget only
// - single-product-review: the one product needs image+widget
// - all others (roundup, deal, brand-vs-brand, budget-tiers): every product needs image+widget
const heroTypes = new Set(["hero"]);
const heroProductId = heroTypes.has(typeRules.articleType)
  ? (brief.products.find(p => p.specs?.popularityRank === "1") ?? brief.products[0]).id
  : null;

for (const product of brief.products) {
  const img    = placements.find(p => p.productId === product.id && p.type === "image");
  const widget = placements.find(p => p.productId === product.id && p.type === "widget");
  const isHeroStar = product.id === heroProductId;
  const requiresImage = !heroTypes.has(typeRules.articleType) || isHeroStar;

  if (img && widget) pass(`Placements for ${product.id}: image@${img.after_paragraph}, widget@${widget.after_paragraph}`);
  else if (!img && requiresImage) { fail(`Missing image placement for ${product.id}`); failures++; }
  else if (!img) pass(`Placements for ${product.id} (alternative): widget@${widget?.after_paragraph ?? "?"}`);
  else if (!widget) { fail(`Missing widget placement for ${product.id}`); failures++; }
}

// ── 3. Pipeline dry-run ───────────────────────────────────────────────────────
section("3. Pipeline dry-run");

console.log("  → insertPlacements...");
const withPlacements = insertPlacements(article, brief, placements, siteKey);
pass("Placements injected", `${withPlacements.length} chars`);

console.log("  → convertMarkdownToHtml...");
const html = convertMarkdownToHtml(withPlacements);
pass("Markdown→HTML", `${html.length} chars`);

const h1 = extractH1(html);
if (h1) pass("H1 extracted", h1);
else    warn("No H1 found in rendered HTML");

console.log("  → insertAffiliateLinks...");
const { html: finalHtml, warnings } = insertAffiliateLinks(html, brief, siteKey);
if (warnings.length === 0) pass("Affiliate links - all products linked");
else warn("Affiliate link warnings", warnings.join(", "));

// Save rendered HTML for inspection
const outFile = articleFile.replace(/\.json$/, "-rendered.html");
writeFileSync(resolve(outFile), finalHtml, "utf-8");
pass("Rendered HTML saved", outFile);

// ── 4. SEO payload check ──────────────────────────────────────────────────────
section("4. SEO payload");

const seo = articleData.seo;
if (seo.title)            pass("SEO title",         seo.title);
else                      { fail("SEO title MISSING"); failures++; }
if (seo.description)      pass("SEO description",   seo.description.slice(0, 60) + "…");
else                      { fail("SEO description MISSING"); failures++; }
if (seo.slug)             pass("SEO slug",           seo.slug);
else                      { fail("SEO slug MISSING"); failures++; }
if (seo.focus_keyword)    pass("Focus keyword",      seo.focus_keyword);
if (seo.featured_image_product_id) pass("Featured image product", seo.featured_image_product_id);

// ── 5. Quality Scoreboard ─────────────────────────────────────────────────────
section("5. Quality Scoreboard");

let seoScore = 100;
const seoIssues: string[] = [];
const focus = seo.focus_keyword?.toLowerCase() || "";

// SEO checks
if (focus) {
  if (!seo.title?.toLowerCase().includes(focus)) { seoScore -= 15; seoIssues.push("Keyword missing from SEO Title"); }
  if (!seo.description?.toLowerCase().includes(focus)) { seoScore -= 15; seoIssues.push("Keyword missing from Meta Description"); }
  if (!paragraphs[1]?.toLowerCase().includes(focus)) { seoScore -= 10; seoIssues.push("Keyword missing from first body paragraph"); }
}
if (!article.includes("## ")) { seoScore -= 20; seoIssues.push("No H2 headings found"); }

// Voice checks - AI tells from type config
let voiceScore = 100;
const foundTells = typeRules.aiTells.filter(t => article.toLowerCase().includes(t.toLowerCase()));
if (foundTells.length > 0) {
  voiceScore -= Math.min(50, foundTells.length * 10);
}
// Check for spelling consistency (robotstovsugere vs robotstøvsugere)
const hasO = article.includes("robotstovsugere");
const hasOslash = article.includes("robotstøvsugere");
if (hasO && hasOslash) { voiceScore -= 15; foundTells.push("Inconsistent spelling (o vs ø)"); }

// CRO checks - weights from type config
let croScore = 100;
const croIssues: string[] = [];
const lastPara = paragraphs[paragraphs.length - 1]?.toLowerCase() || "";
const { verdictAffiliate, placementDensity } = typeRules.croWeights;

if (!lastPara.includes("http")) {
  croScore -= verdictAffiliate;
  croIssues.push(`No affiliate link in the final verdict (-${verdictAffiliate})`);
}
// CRO placement density - expected count varies by type:
// - hero: 1 image + 1 widget for star + 1 widget per alternative = products.length + 1
// - single-product-review: 1 image + 1 widget = 2
// - all others: 2 per product (image + widget)
const expectedPlacements = heroTypes.has(typeRules.articleType)
  ? brief.products.length + 1
  : typeRules.articleType === "single-product-review"
    ? 2
    : brief.products.length * 2;

if (placements.length < expectedPlacements) {
  croScore -= placementDensity;
  croIssues.push(`Low placement density (-${placementDensity})`);
}

const threshold = typeRules.scoreThreshold;
console.log(`  📊 SEO Score:   ${seoScore}/100 ${seoScore >= threshold ? "✅" : "⚠️"}`);
if (seoIssues.length) seoIssues.forEach(i => console.log(`     - ${i}`));

console.log(`  🗣️ Voice Score: ${voiceScore}/100 ${voiceScore >= threshold ? "✅" : "⚠️"}`);
if (foundTells.length) console.log(`     - Found AI-tells: ${foundTells.join(", ")}`);

console.log(`  💰 CRO Score:   ${croScore}/100 ${croScore >= threshold ? "✅" : "⚠️"}`);
if (croIssues.length) croIssues.forEach(i => console.log(`     - ${i}`));

// ── Summary ───────────────────────────────────────────────────────────────────
section("Summary");
if (failures === 0) {
  console.log("  🎉 All checks passed! Article is ready for publishing.\n");
} else {
  console.log(`  ⛔  ${failures} check(s) failed. Fix before publishing.\n`);
  process.exit(1);
}
