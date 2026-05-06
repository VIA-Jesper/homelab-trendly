import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { fetchProductsByCategory, CATEGORY_MAP } from "../src/scraper/pricerunner-client.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const OUT_PATH = join(__dirname, "../data/products.json");

// Delay between category fetches to avoid rate-limiting
const INTER_CATEGORY_DELAY_MS = 2_000;

async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function seed(): Promise<void> {
  const categories = Object.keys(CATEGORY_MAP);
  console.log(`[seed] Fetching ${categories.length} categories from PriceRunner…`);

  const allProducts = [];

  for (const [i, slug] of categories.entries()) {
    console.log(`[seed] (${i + 1}/${categories.length}) ${slug}`);
    try {
      const products = await fetchProductsByCategory(slug, 10);
      allProducts.push(...products);
      console.log(`[seed]   → ${products.length} products`);
    } catch (err) {
      console.error(`[seed]   ✗ Failed: ${err instanceof Error ? err.message : err}`);
    }
    if (i < categories.length - 1) await sleep(INTER_CATEGORY_DELAY_MS);
  }

  mkdirSync(join(__dirname, "../data"), { recursive: true });
  writeFileSync(OUT_PATH, JSON.stringify(allProducts, null, 2), "utf-8");
  console.log(`[seed] ✅ Wrote ${allProducts.length} products to data/products.json`);
}

seed().catch((err) => {
  console.error("[seed] Fatal error:", err);
  process.exit(1);
});
