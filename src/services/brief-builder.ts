/**
 * Brief Builder
 *
 * Fetches live products from PriceRunner for a given category, applies duplicate
 * and cooldown guards, then writes a brief JSON file ready for the generator.
 *
 * Usage (from orchestrator or script):
 *   const result = await buildBriefForCategory("robotstovsugere", "techblog");
 *   if (result.ok) { // brief written to result.briefPath }
 */

import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { v4 as uuidv4 } from "uuid";
import { readFileSync, existsSync } from "fs";

import { fetchProductsByCategoryId } from "../scraper/pricerunner-client.js";
import { getUsedProductIds } from "./content-registry.js";
import { wasPublishedRecently } from "./duplicate-guard.js";
import { classifyProducts } from "./article-classifier.js";
import { SITE_CONFIGS } from "../config/sites.js";
import type { ArticleType, ContentBrief, ImageRef } from "../types/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = join(__dirname, "../..");
const CONFIG_PATH = join(PROJECT_ROOT, "config/categories.json");
const PROMPTS_DIR = join(PROJECT_ROOT, "prompts");

// ─── Category config types ────────────────────────────────────────────────────

interface CategoryEntry {
  name: string;
  slug: string;
  pricerunnerCategoryId: string;
  cooldownDays: number;
  enabled: boolean;
  afFilters?: Array<{ attributeId: string; valueId: string }>;
}

interface CategoriesConfig {
  sites: Record<string, { categories: CategoryEntry[] }>;
}

function loadCategoryConfig(): CategoriesConfig {
  if (!existsSync(CONFIG_PATH)) throw new Error(`Missing config/categories.json`);
  return JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as CategoriesConfig;
}

// ─── Result types ─────────────────────────────────────────────────────────────

export type BriefBuilderResult =
  | { ok: true; briefPath: string; brief: ContentBrief; categorySlug: string }
  | { ok: false; reason: "cooldown" | "no_fresh_products" | "category_not_found" | "disabled"; detail: string };

// ─── Core builder ─────────────────────────────────────────────────────────────

/**
 * Builds a brief for a specific category slug (e.g. "robotstovsugere").
 * Checks cooldown, fetches live products, filters used IDs, writes the brief file.
 *
 * @param overrideArticleType - If provided, bypasses the classifier and uses this type.
 *   The classifier suggestion is still computed and stored as `classifierSuggestion` for logging.
 */
export async function buildBriefForCategory(
  categorySlug: string,
  siteKey = "techblog",
  overrideArticleType?: ArticleType
): Promise<BriefBuilderResult> {
  const config = loadCategoryConfig();
  const siteCategories = config.sites[siteKey]?.categories ?? [];
  const cat = siteCategories.find((c) => c.slug === categorySlug);

  if (!cat) return { ok: false, reason: "category_not_found", detail: `"${categorySlug}" not found in config/categories.json for site "${siteKey}"` };
  if (!cat.enabled) return { ok: false, reason: "disabled", detail: `Category "${categorySlug}" is disabled` };

  // Cooldown check
  if (wasPublishedRecently(siteKey, categorySlug, cat.cooldownDays)) {
    return { ok: false, reason: "cooldown", detail: `"${categorySlug}" published within last ${cat.cooldownDays} days` };
  }

  // Fetch live products
  const siteConfig = SITE_CONFIGS[siteKey];
  const country = siteConfig?.pricerunnerCountry ?? "DK";
  const afFilters = cat.afFilters;
  const allProducts = await fetchProductsByCategoryId(cat.pricerunnerCategoryId, country, 30, afFilters);

  // Filter already-used product IDs
  const usedIds = getUsedProductIds(siteKey);
  const fresh = allProducts
    .filter((p) => !usedIds.includes(p.id))
    .sort((a, b) => b.popularityScore - a.popularityScore)
    .slice(0, 5);

  if (fresh.length < 3) {
    return { ok: false, reason: "no_fresh_products", detail: `Only ${fresh.length} fresh products for "${categorySlug}" (need ≥ 3)` };
  }

  // Build brief
  const images: ImageRef[] = fresh.map((p) => ({
    productId: p.id,
    url: p.imageUrl,
    alt: `${p.name} — ${Object.values(p.specs).slice(0, 2).join(", ")}`,
    caption: `${p.name} hos ${p.retailer || "PriceRunner"} — ${p.priceKr.toLocaleString("da-DK")} kr.`,
  }));

  const classified = classifyProducts(fresh);
  const articleType: ArticleType = overrideArticleType ?? classified.articleType;
  const articleHook = overrideArticleType
    ? classified.articleHook   // keep hook even on override (orchestrator can replace)
    : classified.articleHook;

  if (overrideArticleType) {
    console.log(`[brief-builder] Classifier suggested "${classified.articleType}" — overridden to "${overrideArticleType}"`);
  } else {
    console.log(`[brief-builder] Classifier selected "${articleType}"`);
  }

  const brief: ContentBrief = {
    brief_id: uuidv4(),
    category: categorySlug,
    products: fresh.map(({ imageUrl: _i, popularityScore: _s, outOfStock: _o, ...rest }) => rest),
    images,
    writing_rules: siteConfig?.writingRules ?? { tone: "analytical", minWords: 800, maxWords: 1400, includeProsCons: true, includeVerdict: true },
    compliance: {
      requireDisclosure: false,
      disclosurePhrases: ["indeholder affiliatelinks", "vi tjener kommission", "annonce", "reklame"],
      forbiddenSuperlatives: ["bedste på markedet", "billigst i danmark", "nr. 1 valg", "absolut bedst"],
    },
    articleType,
    articleHook,
  };

  // Write to prompts/
  mkdirSync(PROMPTS_DIR, { recursive: true });
  const briefPath = join(PROMPTS_DIR, `brief-${categorySlug}-live.json`);
  writeFileSync(briefPath, JSON.stringify({ job_id: uuidv4(), brief }, null, 2), "utf-8");
  console.log(`[brief-builder] Brief written to ${briefPath} (${fresh.length} products)`);

  return { ok: true, briefPath, brief, categorySlug };
}

/**
 * Picks the best available category for a site (not in cooldown, most fresh products).
 * Used by the automated scheduler to decide what to generate next.
 */
export async function pickNextCategory(siteKey = "techblog"): Promise<BriefBuilderResult> {
  const config = loadCategoryConfig();
  const siteCategories = (config.sites[siteKey]?.categories ?? []).filter((c) => c.enabled);
  const siteConfig = SITE_CONFIGS[siteKey];
  const country = siteConfig?.pricerunnerCountry ?? "DK";

  const candidates: Array<{ cat: CategoryEntry; freshCount: number }> = [];

  for (const cat of siteCategories) {
    if (wasPublishedRecently(siteKey, cat.slug, cat.cooldownDays)) continue;
    try {
      const afFilters = cat.afFilters;
      const all = await fetchProductsByCategoryId(cat.pricerunnerCategoryId, country, 30, afFilters);
      const usedIds = getUsedProductIds(siteKey);
      const fresh = all.filter((p) => !usedIds.includes(p.id));
      if (fresh.length >= 3) candidates.push({ cat, freshCount: fresh.length });
    } catch (err) {
      console.warn(`[brief-builder] Failed to fetch "${cat.slug}":`, err);
    }
  }

  if (candidates.length === 0) {
    return { ok: false, reason: "no_fresh_products", detail: "All categories are either in cooldown or exhausted" };
  }

  candidates.sort((a, b) => b.freshCount - a.freshCount);
  return buildBriefForCategory(candidates[0]!.cat.slug, siteKey);
}
