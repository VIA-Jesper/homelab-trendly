/**
 * Dynamic category discovery via the PriceRunner suggest API.
 *
 * Given a site's rootCategories config (search terms + cooldown), queries PR's
 * autocomplete endpoint to find live subcategories, fetches products for each,
 * scores them by demand signal + freshness, and returns the best candidate not
 * currently in cooldown.
 */

import axios from "axios";
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { fetchProductsByCategoryId, withBackoff } from "../scraper/pricerunner-client.js";
import { wasPublishedRecently } from "./duplicate-guard.js";
import { SITE_CONFIGS } from "../config/sites.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const CONFIG_PATH = join(__dirname, "../../config/categories.json");

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

// ─── Config types ─────────────────────────────────────────────────────────────

interface RootCategory {
  name: string;
  label: string;
  searchTerms: string[];
  defaultCooldownDays: number;
}

interface CategoriesConfig {
  sites: Record<string, { rootCategories?: RootCategory[] }>;
}

function loadConfig(): CategoriesConfig {
  if (!existsSync(CONFIG_PATH)) throw new Error("[category-discoverer] Missing config/categories.json");
  return JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as CategoriesConfig;
}

// ─── Result type ──────────────────────────────────────────────────────────────

export interface DiscoveredCategory {
  categoryId: string;
  /** Transliterated, hyphenated slug derived from the PR category name */
  categorySlug: string;
  categoryName: string;
  rootName: string;
  score: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Transliterate Danish chars and slugify a display name */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/æ/g, "ae").replace(/ø/g, "oe").replace(/å/g, "aa")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** PR suggest endpoint → list of category hits for a search term */
async function suggestCategories(
  term: string,
  base: string,
  countryUpper: string,
  countryLower: string
): Promise<{ id: string; name: string }[]> {
  type Hit = { id?: string; name?: string; type?: string; url?: string };
  type Resp = { suggestions?: Hit[] };

  const data = await withBackoff(async () => {
    const res = await axios.get<Resp>(
      `${base}/${countryLower}/api/instant-search-edge-rest/public/search/suggest/${countryUpper}`,
      {
        params: { q: term },
        headers: { "User-Agent": UA, Accept: "application/json" },
        timeout: 8_000,
      }
    );
    return res.data;
  });

  const results: { id: string; name: string }[] = [];
  for (const s of data.suggestions ?? []) {
    if (s.type !== "CATEGORY") continue;
    const id = s.id ?? (/(\d+)$/.exec(s.url ?? "")?.[1]);
    if (id && s.name) results.push({ id, name: s.name });
  }
  return results;
}

/** Score a category based on watcher ribbon density, price spread, and freshness */
function scoreCategory(
  watchedCount: number,
  priceSpread: number,
  daysSince: number | null,
  cooldownDays: number
): number {
  const freshnessScore = daysSince === null ? 30 : Math.min(daysSince / cooldownDays, 1) * 30;
  const watcherScore = Math.min(watchedCount * 5, 40);
  const spreadScore = Math.min(priceSpread * 15, 30);
  return watcherScore + spreadScore + freshnessScore;
}

// ─── Main export ──────────────────────────────────────────────────────────────

/**
 * Discovers the best PriceRunner subcategory to write about next for the given site.
 *
 * - Skips any category whose slug was published within its cooldown window.
 * - Skips categories with fewer than 3 available products.
 * - Returns the highest-scoring candidate, or null if none qualify.
 */
export async function discoverBestCategory(siteKey: string): Promise<DiscoveredCategory | null> {
  const config = loadConfig();
  const rootCategories = config.sites[siteKey]?.rootCategories ?? [];

  if (rootCategories.length === 0) {
    console.warn(`[category-discoverer] No rootCategories configured for "${siteKey}"`);
    return null;
  }

  const siteConfig = SITE_CONFIGS[siteKey];
  const country = siteConfig?.pricerunnerCountry ?? "DK";
  const countryUpper = country.toUpperCase();
  const countryLower = country.toLowerCase();
  const base = `https://www.pricerunner.${countryLower === "gb" ? "com" : countryLower}`;

  const candidates: DiscoveredCategory[] = [];

  for (const root of rootCategories) {
    const seen = new Set<string>();

    for (const term of root.searchTerms) {
      let hits: { id: string; name: string }[];
      try {
        hits = await suggestCategories(term, base, countryUpper, countryLower);
      } catch (err) {
        console.warn(`[category-discoverer] Suggest failed for "${term}":`, err);
        await new Promise((r) => setTimeout(r, 500));
        continue;
      }

      for (const hit of hits) {
        if (seen.has(hit.id)) continue;
        seen.add(hit.id);

        const categorySlug = slugify(hit.name);

        if (wasPublishedRecently(siteKey, categorySlug, root.defaultCooldownDays)) {
          console.log(`[category-discoverer] "${hit.name}" in cooldown — skipping`);
          continue;
        }

        let products;
        try {
          products = await fetchProductsByCategoryId(hit.id, country, 20);
        } catch {
          continue;
        }
        if (products.length < 3) continue;

        const watched = products.filter((p) => p.specs["ribbon"] === "WATCHED").length;
        const prices = products.map((p) => p.priceKr).filter(Boolean);
        const priceSpread =
          prices.length > 1 ? Math.max(...prices) / Math.min(...prices) - 1 : 0;
        const score = scoreCategory(watched, priceSpread, null, root.defaultCooldownDays);

        candidates.push({ categoryId: hit.id, categorySlug, categoryName: hit.name, rootName: root.name, score });
      }

      await new Promise((r) => setTimeout(r, 500)); // polite gap between terms
    }
  }

  if (candidates.length === 0) return null;

  candidates.sort((a, b) => b.score - a.score);
  const best = candidates[0]!;
  console.log(
    `[category-discoverer] Best: "${best.categoryName}" (${best.categoryId}) ` +
    `root="${best.rootName}" score=${best.score.toFixed(1)}`
  );
  return best;
}
