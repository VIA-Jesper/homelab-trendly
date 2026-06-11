import axios from "axios";
import type { RawProduct } from "../services/product-store.js";

// ─── User-Agent rotation ─────────────────────────────────────────────────────
const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
  "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
];

function randomUA(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)]!;
}

// ─── Exponential backoff ─────────────────────────────────────────────────────
export async function withBackoff<T>(fn: () => Promise<T>, maxRetries = 4): Promise<T> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const retryable = status === 429 || status === 503 || (status !== undefined && status >= 500);
      if (!retryable || attempt === maxRetries) throw err;
      const delayMs = Math.min(1000 * 2 ** attempt + Math.random() * 500, 30_000);
      console.warn(`[pricerunner] HTTP ${status} - retry ${attempt + 1}/${maxRetries} in ${Math.round(delayMs)}ms`);
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw new Error("unreachable");
}

// ─── PriceRunner base URLs per country ───────────────────────────────────────
const PR_BASE_BY_COUNTRY: Record<string, string> = {
  DK: "https://www.pricerunner.dk",
  SE: "https://www.pricerunner.se",
  GB: "https://www.pricerunner.com",
};

function getBase(country: string): string {
  return PR_BASE_BY_COUNTRY[country.toUpperCase()] ?? "https://www.pricerunner.dk";
}

// ─── Rate limiting (1000ms minimum between requests) ─────────────────────────
let _lastRequestAt = 0;
async function rateLimit(): Promise<void> {
  const now = Date.now();
  const elapsed = now - _lastRequestAt;
  if (elapsed < 1000) await new Promise((r) => setTimeout(r, 1000 - elapsed));
  _lastRequestAt = Date.now();
}

// ─── 24-hour in-memory cache ──────────────────────────────────────────────────
interface CacheEntry<T> { data: T; expiresAt: number }
const _cache = new Map<string, CacheEntry<unknown>>();
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

function cacheGet<T>(key: string): T | undefined {
  const entry = _cache.get(key);
  if (!entry || Date.now() > entry.expiresAt) { _cache.delete(key); return undefined; }
  return entry.data as T;
}
function cacheSet<T>(key: string, data: T): void {
  _cache.set(key, { data, expiresAt: Date.now() + CACHE_TTL_MS });
}

// ─── v4 API response types ────────────────────────────────────────────────────
export interface V4Product {
  id: string;
  name: string;
  lowestPrice?: { amount: string; currency: string };
  cheapestOffer?: { price?: { amount: number }; merchant?: { name: string } };
  image?: { url?: string; path?: string };
  url?: string;
  brand?: { name: string };
  description?: string;
  rating?: { average: number; count: number };
  ribbon?: { type: string; value?: string };
  priceDrop?: { percent: number };
  topOffers?: Array<{ merchant?: { name: string } }>;
  rank?: { rank: number };
  previewMerchants?: { count: number };
  outOfStock?: boolean;
}

interface V4CategoryResponse {
  products?: V4Product[];
  // category browse endpoint wraps in results
  results?: V4Product[];
}

interface V4SuggestHit {
  id?: string;
  name?: string;
  type?: string;   // "CATEGORY" | "BRAND" | "PRODUCT" etc.
  url?: string;
}

interface V4SuggestResponse {
  products?: V4Product[];       // usually empty for keyword queries
  suggestions?: V4SuggestHit[]; // category/brand autocomplete hints
}

// ─── Maps PriceRunner category ID → our internal category name ───────────────
export const CATEGORY_ID_MAP: Record<string, string> = {
  "27": "laptops",
  "94": "headphones",
  "1": "phones",
  "2": "tvs",
  // Hjem & Husholdning
  "81": "frituregryder-airfryere",
  "82": "kaffemaskiner",
  "250": "ismaskiner",
  "14": "vaskemaskiner",
  "1613": "robotstoevsugere",
  // Have & Udemiljø
  "1595": "robotplaeneklippere",
  "335": "grill",
  "120": "havemaskiner",
  "638": "hojtryks-hedvandsrensere",
  // Værktøj
  "345": "elvaerktoej",
  "1258": "bore-skruemaskiner",
  "1260": "elsave",
};

// Legacy slug map kept for seed script compatibility
export const CATEGORY_MAP: Record<string, string> = {
  "baerbare-computere-17": "laptops",
  "hoeretelefoner-2451": "headphones",
  "mobiltelefoner-1": "phones",
  "tv-1344": "tvs",
};

function makeAbsoluteUrl(url: string | undefined, base: string): string {
  if (!url) return base;
  if (url.startsWith("http")) return url;
  return `${base}${url}`;
}

/** Compute a popularity score for ranking products within a category.
 *  Higher = more demand signal. Used by product-store to pick the best products.
 *
 *  Scoring:
 *    watchedCount  →  200+ = 40pts, 100+ = 30pts, 50+ = 20pts, any ribbon = 10pts
 *    rank.rank     →  1 = 30pts, 2 = 25pts, 3 = 20pts, top10 = 10pts, else 0
 *    rating        →  ≥4.5 × ln(reviews+1) bonus (max 20pts)
 *    merchantCount →  >20 = 5pts, >10 = 3pts, >5 = 1pt
 */
export function computePopularityScore(p: V4Product): number {
  let score = 0;

  // Watcher ribbon
  const ribbonVal = p.ribbon?.value ?? "";
  const watchNum = parseInt(ribbonVal, 10);
  if (!isNaN(watchNum)) {
    if (watchNum >= 200) score += 40;
    else if (watchNum >= 100) score += 30;
    else if (watchNum >= 50) score += 20;
    else score += 10;
  } else if (p.ribbon?.type === "WATCHED") {
    score += 10;
  }

  // Popularity rank
  const rank = p.rank?.rank;
  if (rank !== undefined) {
    if (rank === 1) score += 30;
    else if (rank === 2) score += 25;
    else if (rank === 3) score += 20;
    else if (rank <= 10) score += 10;
  }

  // Rating quality × log(volume)
  const avg = p.rating?.average ?? 0;
  const cnt = p.rating?.count ?? 0;
  if (avg >= 4.5 && cnt > 0) {
    score += Math.min(20, Math.round(avg * Math.log(cnt + 1)));
  }

  // Merchant depth
  const merchants = p.previewMerchants?.count ?? 0;
  if (merchants > 20) score += 5;
  else if (merchants > 10) score += 3;
  else if (merchants > 5) score += 1;

  return score;
}

export function mapV4Product(p: V4Product, base: string, internalCategory: string): RawProduct {
  const priceRaw = p.lowestPrice?.amount;
  const priceKr = priceRaw !== undefined
    ? parseFloat(priceRaw)
    : (p.cheapestOffer?.price?.amount ?? 0);

  const imageUrl = makeAbsoluteUrl(p.image?.url ?? p.image?.path, base);
  const affiliateUrl = makeAbsoluteUrl(p.url, base);

  // Retailer: prefer cheapestOffer merchant (same price we display), fall back to topOffers
  const retailer =
    p.cheapestOffer?.merchant?.name ??
    p.topOffers?.[0]?.merchant?.name ??
    "PriceRunner";

  const specs: Record<string, string> = {};
  if (p.brand?.name) specs["brand"] = p.brand.name;
  if (p.description) specs["description"] = p.description;
  if (p.rating?.average !== undefined) specs["rating"] = `${p.rating.average} (${p.rating.count ?? 0} reviews)`;
  if (p.ribbon?.type) specs["ribbon"] = p.ribbon.type;
  if (p.ribbon?.type === "WATCHED" && p.ribbon?.value) {
    // Format as integer count with "+" suffix, strip any minus sign
    const num = Math.abs(parseFloat(p.ribbon.value));
    specs["watchedLabel"] = `${Math.round(num)}+`;
  }
  if (p.priceDrop?.percent !== undefined) specs["priceDrop"] = `${p.priceDrop.percent}%`;
  if (p.rank?.rank !== undefined) specs["popularityRank"] = String(p.rank.rank);
  if (p.previewMerchants?.count !== undefined) specs["merchantCount"] = String(p.previewMerchants.count);

  const popularityScore = computePopularityScore(p);
  if (popularityScore > 0) specs["popularityScore"] = String(popularityScore);

  return {
    id: `pr_${p.id}`,
    name: p.name,
    category: internalCategory,
    priceKr,
    retailer,
    affiliateUrl,
    imageUrl,
    popularityScore,
    outOfStock: p.outOfStock ?? false,
    specs,
  };
}

// ─── Category Browse v4 ───────────────────────────────────────────────────────
export interface AfFilter {
  attributeId: string;
  valueId: string;
}

export async function fetchProductsByCategoryId(
  categoryId: string,
  country = "DK",
  size = 30,
  afFilters?: AfFilter[]
): Promise<RawProduct[]> {
  const filterKey = afFilters?.map(f => `${f.attributeId}=${f.valueId}`).join(':') ?? '';
  const cacheKey = `pricerunner-category:${categoryId}:${country}:${filterKey}`;
  const cached = cacheGet<RawProduct[]>(cacheKey);
  if (cached) return cached;

  await rateLimit();
  const base = getBase(country);
  const countryUpper = country.toUpperCase();
  const countryLower = country.toLowerCase();
  const internalCategory = CATEGORY_ID_MAP[categoryId] ?? categoryId;

  const results = await withBackoff(async () => {
    const params: Record<string, string | number> = { size, sorting: "POPULARITY", device: "desktop" };
    if (afFilters) {
      for (const f of afFilters) {
        params[`af_${f.attributeId}`] = f.valueId;
      }
    }
    const res = await axios.get<V4CategoryResponse>(
      `${base}/${countryLower}/api/search-edge-rest/public/search/category/v4/${countryUpper}/${categoryId}`,
      {
        params,
        headers: { "User-Agent": randomUA(), "Accept": "application/json" },
        timeout: 15_000,
      }
    );
    return res.data.products ?? res.data.results ?? [];
  });

  const mapped = results.map((p) => mapV4Product(p, base, internalCategory));
  cacheSet(cacheKey, mapped);
  return mapped;
}

// ─── Keyword Search (suggest endpoint) ───────────────────────────────────────
export async function searchProductsByKeyword(
  term: string,
  country = "DK"
): Promise<RawProduct[]> {
  await rateLimit();
  const base = getBase(country);
  const countryUpper = country.toUpperCase();
  const countryLower = country.toLowerCase();

  const results = await withBackoff(async () => {
    const res = await axios.get<V4SuggestResponse>(
      `${base}/${countryLower}/api/instant-search-edge-rest/public/search/suggest/${countryUpper}`,
      {
        params: { q: term },
        headers: { "User-Agent": randomUA(), "Accept": "application/json" },
        timeout: 10_000,
      }
    );
    return res.data.products ?? [];
  });

  return results.map((p) => mapV4Product(p, base, "unknown"));
}

// ─── Legacy: category slug → v4 by mapping category ID ───────────────────────
/** Used by the seed script. Maps old slug names to IDs and calls v4. */
export async function fetchProductsByCategory(
  categorySlug: string,
  limit = 10
): Promise<RawProduct[]> {
  // Extract numeric ID from slug (e.g. "baerbare-computere-17" → "17")
  const match = /(\d+)$/.exec(categorySlug);
  const categoryId = match?.[1];
  if (!categoryId) throw new Error(`Cannot extract category ID from slug: ${categorySlug}`);
  const products = await fetchProductsByCategoryId(categoryId, "DK", Math.max(limit, 30));
  return products.slice(0, limit);
}

// ─── Category Tree Discovery ─────────────────────────────────────────────────

interface MenuCategory {
  id: string;
  name: string;
  url?: string | null;
  children?: Array<{ id: string; name: string; url?: string | null }>;
}

interface MenuResponse {
  id: string;
  name: string;
  categories: MenuCategory[];
}

export interface DiscoveredLeafCategory {
  id: string;
  name: string;
  parentId: string;
  parentName: string;
}

/** Discover all leaf categories under a PriceRunner topic.
 *  Hits the navigation/menu endpoint once, caches to disk.
 *  Topic IDs look like "t34", "t1424" etc.
 */
export async function discoverLeafCategories(
  topicId: string,
  country = "DK"
): Promise<DiscoveredLeafCategory[]> {
  const cacheKey = `pricerunner-tree:${topicId}:${country}`;
  const cached = cacheGet<DiscoveredLeafCategory[]>(cacheKey);
  if (cached) return cached;

  await rateLimit();
  const base = getBase(country);
  const countryLower = country.toLowerCase();
  const countryUpper = country.toUpperCase();

  const res = await withBackoff(async () => {
    return axios.get<MenuResponse>(
      `${base}/${countryLower}/api/seo-edge-rest/public/navigation/menu/${countryUpper}/hierarchy/${topicId}`,
      {
        headers: { "User-Agent": randomUA(), "Accept": "application/json" },
        timeout: 15_000,
      }
    );
  });

  const data = res.data;
  const leaves: DiscoveredLeafCategory[] = [];

  for (const cat of data.categories ?? []) {
    if (cat.children && cat.children.length > 0) {
      for (const child of cat.children) {
        // Skip filter combinations (IDs with dashes like "100003649-100015017")
        if (/\d+-\d+/.test(child.id)) continue;
        leaves.push({
          id: child.id,
          name: child.name,
          parentId: cat.id,
          parentName: cat.name,
        });
      }
    }
  }

  cacheSet(cacheKey, leaves);
  return leaves;
}

/** Extract topic ID from a PriceRunner URL.
 *  Supports /t/{id}/Name and /cl/{id}/Name formats.
 */
export function extractTopicIdFromUrl(url: string): string | null {
  const tMatch = /\/t\/(\d+)\/[^\/]*$/.exec(url);
  if (tMatch) return `t${tMatch[1]}`;
  const clMatch = /\/cl\/(\d+)\/[^\/]*$/.exec(url);
  if (clMatch) return `cl${clMatch[1]}`;
  return null;
}
