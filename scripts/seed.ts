import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { fetchProductsByCategoryId, CATEGORY_ID_MAP } from "../src/scraper/pricerunner-client.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const OUT_PATH = join(__dirname, "../data/products.json");

async function seed(): Promise<void> {
  const categoryIds = Object.keys(CATEGORY_ID_MAP);
  console.log(`[seed] Fetching ${categoryIds.length} categories from PriceRunner v4 API…`);

  const allProducts = [];

  for (const [i, categoryId] of categoryIds.entries()) {
    const name = CATEGORY_ID_MAP[categoryId];
    console.log(`[seed] (${i + 1}/${categoryIds.length}) categoryId=${categoryId} (${name})`);
    try {
      // Rate limiting is handled inside fetchProductsByCategoryId (1000ms min interval)
      const products = await fetchProductsByCategoryId(categoryId, "DK", 30);
      allProducts.push(...products);
      console.log(`[seed]   → ${products.length} products`);
    } catch (err) {
      console.error(`[seed]   ✗ Failed: ${err instanceof Error ? err.message : err}`);
    }
  }

  mkdirSync(join(__dirname, "../data"), { recursive: true });
  writeFileSync(OUT_PATH, JSON.stringify(allProducts, null, 2), "utf-8");
  console.log(`[seed] ✅ Wrote ${allProducts.length} products to data/products.json`);
}

seed().catch((err) => {
  console.error("[seed] Fatal error:", err);
  process.exit(1);
});
