import { v4 as uuidv4 } from "uuid";
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import type { ContentBrief, ImageRef, WritingRules, ComplianceRules } from "../types/index.js";
import { getProductsByCategory, getProductByUrl, getImageUrl } from "./product-store.js";
import { SITE_CONFIGS } from "../config/sites.js";
import { getUsedProductIds } from "./content-registry.js";
import { getMostUnwrittenLeafCategory, getFreshProductsForCategory } from "./category-traversal.js";
import { fetchProductsByCategoryId } from "../scraper/pricerunner-client.js";
import type { RawProduct } from "./product-store.js";
import { classifyProducts } from "./article-classifier.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const CATEGORIES_CONFIG_PATH = join(__dirname, "../../config/categories.json");

/** Looks up the PriceRunner category ID for a slug from config/categories.json */
interface CategoryConfig {
  slug: string;
  pricerunnerCategoryId: string;
  afFilters?: Array<{ attributeId: string; valueId: string }>;
}

function getPrCategoryConfig(siteKey: string, categorySlug: string): CategoryConfig | undefined {
  try {
    if (!existsSync(CATEGORIES_CONFIG_PATH)) return undefined;
    const config = JSON.parse(readFileSync(CATEGORIES_CONFIG_PATH, "utf-8")) as {
      sites: Record<string, { categories: CategoryConfig[] }>;
    };
    const normalise = (s: string) => s.replace(/ø/g, 'oe').replace(/æ/g, 'ae').replace(/å/g, 'aa');
    const needle = normalise(categorySlug);
    return config.sites[siteKey]?.categories.find((c) => {
      const hay = normalise(c.slug);
      return hay === needle || hay.startsWith(needle);
    });
  } catch {
    return undefined;
  }
}

const DEFAULT_WRITING_RULES: WritingRules = {
  tone: "neutral", minWords: 600, maxWords: 1200,
  includeProsCons: true, includeVerdict: true,
};

function loadComplianceRules(): ComplianceRules {
  try {
    const configPath = join(__dirname, "../../config/compliance-rules.json");
    const raw = readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw) as {
      requireDisclosure: boolean;
      disclosurePhrases: string[];
      forbiddenSuperlatives: string[];
    };
    return {
      requireDisclosure: config.requireDisclosure ?? true,
      disclosurePhrases: config.disclosurePhrases ?? [],
      forbiddenSuperlatives: config.forbiddenSuperlatives ?? [],
    };
  } catch {
    console.warn("[brief-generator] Could not load compliance-rules.json — using defaults");
    return {
      requireDisclosure: true,
      disclosurePhrases: ["indeholder affiliatelinks", "vi tjener kommission", "annonce", "reklame"],
      forbiddenSuperlatives: ["bedste på markedet", "billigst i danmark", "nr. 1 valg", "absolut bedst"],
    };
  }
}

const DEFAULT_COMPLIANCE: ComplianceRules = loadComplianceRules();

export type BriefError =
  | { error: "category_exhausted"; category: string }
  | { error: "all_categories_exhausted" }
  | { error: "product_not_found"; productUrl: string };

function buildBrief(
  products: RawProduct[],
  resolvedCategory: string,
  siteKey: string
): ContentBrief {
  const siteConfig = SITE_CONFIGS[siteKey];
  const writingRules = siteConfig?.writingRules ?? DEFAULT_WRITING_RULES;

  const images: ImageRef[] = products.map((p) => ({
    productId: p.id,
    url: p.imageUrl || getImageUrl(p.id),
    alt: `${p.name} — ${Object.values(p.specs).slice(0, 2).join(", ")}`,
    caption: `${p.name} hos ${p.retailer} — ${p.priceKr.toLocaleString("da-DK")} kr.`,
  }));

  const { articleType, articleHook } = classifyProducts(products);

  return {
    brief_id: uuidv4(),
    category: resolvedCategory,
    // Strip internal fields before exposing as ProductBrief
    products: products.map(({ imageUrl: _i, popularityScore: _s, outOfStock: _o, ...rest }) => rest),
    images,
    writing_rules: writingRules,
    compliance: DEFAULT_COMPLIANCE,
    articleType,
    articleHook,
  };
}

/**
 * Async variant — uses live PriceRunner data when available, falls back to product store.
 *
 * @param pricerunnerCategoryId - When provided (e.g. from dynamic discovery), fetches products
 *   directly from PR by category ID, bypassing the pre-configured traversal list. The `category`
 *   param is still used as the human-readable slug stored in the brief.
 */
export async function generateBriefAsync(
  category: string | undefined,
  productUrl: string | undefined,
  siteKey = "techblog",
  pricerunnerCategoryId?: string
): Promise<ContentBrief | BriefError> {
  if (productUrl) {
    const single = getProductByUrl(productUrl);
    if (!single) return { error: "product_not_found", productUrl };
    return buildBrief([single], single.category, siteKey);
  }

  const siteConfig = SITE_CONFIGS[siteKey];
  const country = siteConfig?.pricerunnerCountry ?? "DK";

  // Fast path: caller already discovered a specific PR category ID (e.g. via category-discoverer)
  if (pricerunnerCategoryId) {
    try {
      const usedIds = getUsedProductIds(siteKey);
      const all = await fetchProductsByCategoryId(pricerunnerCategoryId, country, 30);
      const fresh = all.filter((p) => !usedIds.includes(p.id));
      const resolvedCategory = category ?? pricerunnerCategoryId;
      if (fresh.length < 3) return { error: "category_exhausted", category: resolvedCategory };
      return buildBrief(fresh.slice(0, 5), resolvedCategory, siteKey);
    } catch (err) {
      console.warn("[brief-generator] Direct categoryId fetch failed, falling back:", err);
    }
  }

  // Try live PriceRunner category traversal (pre-configured category IDs)
  try {
    if (category) {
      const freshProducts = await getFreshProductsForCategory(siteKey, category);
      if (freshProducts) return buildBrief(freshProducts.slice(0, 5), category, siteKey);

      // Traversal didn't know this category — look up its PR ID from categories.json and fetch directly
      const catConfig = getPrCategoryConfig(siteKey, category);
      if (catConfig) {
        console.log(`[brief-generator] "${category}" not in traversal cache — fetching by ID ${catConfig.pricerunnerCategoryId}`);
        const usedIds = getUsedProductIds(siteKey);
        const all = await fetchProductsByCategoryId(catConfig.pricerunnerCategoryId, country, 30, catConfig.afFilters);
        const fresh = all.filter((p) => !usedIds.includes(p.id));
        if (fresh.length < 3) return { error: "category_exhausted", category };
        return buildBrief(fresh.slice(0, 5), category, siteKey);
      }

      return { error: "category_exhausted", category };
    } else {
      const leaf = await getMostUnwrittenLeafCategory(siteKey);
      if (!leaf) return { error: "all_categories_exhausted" };
      return buildBrief(leaf.freshProducts.slice(0, 5), leaf.categoryName, siteKey);
    }
  } catch (err) {
    console.warn("[brief-generator] Live PR lookup failed, falling back to product store:", err);
  }

  // Last resort: local product store with registry filtering
  const usedIds = getUsedProductIds(siteKey);
  const resolvedCategory = category ?? "general";
  const allProducts = getProductsByCategory(resolvedCategory);
  const fresh = allProducts.filter((p) => !usedIds.includes(p.id));

  if (fresh.length < 3) return { error: "category_exhausted", category: resolvedCategory };
  return buildBrief(fresh.slice(0, 5), resolvedCategory, siteKey);
}

/** Sync variant kept for backward compat with existing REST route */
export function generateBrief(
  category: string | undefined,
  productUrl: string | undefined,
  siteKey = "techblog"
): ContentBrief {
  const siteConfig = SITE_CONFIGS[siteKey];
  const writingRules = siteConfig?.writingRules ?? DEFAULT_WRITING_RULES;

  let products: RawProduct[];
  let resolvedCategory: string;

  if (productUrl) {
    const single = getProductByUrl(productUrl);
    products = single ? [single] : [];
    resolvedCategory = single?.category ?? "unknown";
  } else {
    resolvedCategory = category ?? "general";
    const usedIds = getUsedProductIds(siteKey);
    const all = getProductsByCategory(resolvedCategory);
    products = all.filter((p) => !usedIds.includes(p.id));
  }

  return buildBrief(products, resolvedCategory, siteKey);
}
