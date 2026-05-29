import { fetchProductsByCategoryId } from "../scraper/pricerunner-client.js";
import { SITE_CONFIGS } from "../config/sites.js";
import { getUsedProductIds } from "./content-registry.js";

// ─── 24-hour cache for traversal results ─────────────────────────────────────
interface LeafResult {
  categoryId: string;
  categoryName: string;
  freshProducts: Awaited<ReturnType<typeof fetchProductsByCategoryId>>;
}

interface CacheEntry { data: LeafResult[]; expiresAt: number }
const _cache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

function cacheGet(key: string): LeafResult[] | undefined {
  const entry = _cache.get(key);
  if (!entry || Date.now() > entry.expiresAt) { _cache.delete(key); return undefined; }
  return entry.data;
}
function cacheSet(key: string, data: LeafResult[]): void {
  _cache.set(key, { data, expiresAt: Date.now() + CACHE_TTL_MS });
}

/**
 * Fetches products for all configured PriceRunner categories for the given site,
 * filters out already-published products, and returns per-leaf results.
 *
 * Phase 1: Treats each configured category ID as a leaf.
 * Phase 2: Extend to recursively traverse child categories.
 */
async function fetchLeafResults(siteKey: string): Promise<LeafResult[]> {
  const cacheKey = `traversal:${siteKey}`;
  const cached = cacheGet(cacheKey);
  if (cached) return cached;

  const siteConfig = SITE_CONFIGS[siteKey];
  if (!siteConfig) throw new Error(`Unknown site key: ${siteKey}`);

  const usedIds = getUsedProductIds(siteKey);
  const country = siteConfig.pricerunnerCountry;
  const results: LeafResult[] = [];

  for (const categoryId of siteConfig.pricerunnerCategories) {
    try {
      const allProducts = await fetchProductsByCategoryId(categoryId, country, 30);
      const freshProducts = allProducts.filter((p) => !usedIds.includes(p.id));
      const categoryName = freshProducts[0]?.category ?? categoryId;
      results.push({ categoryId, categoryName, freshProducts });
    } catch (err) {
      console.warn(`[category-traversal] Failed to fetch category ${categoryId}:`, err);
    }
  }

  cacheSet(cacheKey, results);
  return results;
}

/**
 * Returns the leaf category with the most unwritten (fresh) products for the given site.
 * Returns null if all categories are exhausted (< 3 fresh products each).
 */
export async function getMostUnwrittenLeafCategory(siteKey: string): Promise<LeafResult | null> {
  const leaves = await fetchLeafResults(siteKey);
  const viable = leaves.filter((l) => l.freshProducts.length >= 3);
  if (viable.length === 0) return null;
  // Sort descending by fresh product count — pick richest
  viable.sort((a, b) => b.freshProducts.length - a.freshProducts.length);
  return viable[0]!;
}

/**
 * Returns fresh products for a specific category name on a site.
 * Returns null if fewer than 3 fresh products remain.
 */
export async function getFreshProductsForCategory(
  siteKey: string,
  categoryName: string
): Promise<Awaited<ReturnType<typeof fetchProductsByCategoryId>> | null> {
  const leaves = await fetchLeafResults(siteKey);
  const normalise = (s: string) => s.toLowerCase().replace(/ø/g, 'oe').replace(/æ/g, 'ae').replace(/å/g, 'aa');
  const needle = normalise(categoryName);
  const leaf = leaves.find((l) => normalise(l.categoryName) === needle)
    ?? leaves.find((l) => normalise(l.categoryName).startsWith(needle) || needle.startsWith(normalise(l.categoryName)));
  if (!leaf || leaf.freshProducts.length < 3) return null;
  return leaf.freshProducts;
}

/** Invalidates the traversal cache for a site (call after registering new products) */
export function invalidateTraversalCache(siteKey: string): void {
  _cache.delete(`traversal:${siteKey}`);
}
