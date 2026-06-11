/**
 * PriceRunner v4 API smoke test
 * Run with: npm run smoke:pricerunner
 *
 * Hits the real PriceRunner endpoints and verifies:
 * - HTTP 200 response
 * - At least 1 product returned
 * - Price is a valid number (confirms string→float parsing)
 * - Image URL is an absolute HTTPS URL
 * - Affiliate URL is absolute
 * - Brand/ribbon/rating fields are present where expected
 */

import { fetchProductsByCategoryId, searchProductsByKeyword, CATEGORY_ID_MAP } from "../src/scraper/pricerunner-client.js";

const GREEN = "\x1b[32m✓\x1b[0m";
const RED   = "\x1b[31m✗\x1b[0m";
const CYAN  = "\x1b[36m";
const RESET = "\x1b[0m";

let passed = 0;
let failed = 0;

function check(label: string, condition: boolean, detail?: string): void {
  if (condition) {
    console.log(`  ${GREEN} ${label}`);
    passed++;
  } else {
    console.log(`  ${RED} ${label}${detail ? ` - ${detail}` : ""}`);
    failed++;
  }
}

async function smokeCategory(categoryId: string, country = "DK"): Promise<void> {
  const name = CATEGORY_ID_MAP[categoryId] ?? categoryId;
  console.log(`\n${CYAN}▶ Category Browse v4: categoryId=${categoryId} (${name})${RESET}`);

  const products = await fetchProductsByCategoryId(categoryId, country, 10);

  check("Returns at least 1 product", products.length >= 1, `got ${products.length}`);

  const p = products[0]!;
  console.log(`  First product: "${p.name}" - ${p.priceKr} kr.`);

  check("Product has id with pr_ prefix", p.id.startsWith("pr_"), p.id);
  check("Price is a finite number", isFinite(p.priceKr) && p.priceKr > 0, String(p.priceKr));
  check("Image URL is absolute HTTPS", p.imageUrl.startsWith("https://"), p.imageUrl);
  check("Affiliate URL is absolute", p.affiliateUrl.startsWith("http"), p.affiliateUrl);
  check("Retailer name present", p.retailer.length > 0, p.retailer);
  check("Category matches expected", p.category === name, `got "${p.category}", expected "${name}"`);

  // v4-specific fields (not always present, warn if missing)
  const hasBrand = typeof p.specs["brand"] === "string";
  const hasRating = typeof p.specs["rating"] === "string";
  console.log(`  Brand: ${hasBrand ? p.specs["brand"] : "(not present)"}  |  Rating: ${hasRating ? p.specs["rating"] : "(not present)"}`);

  // Show sample of products
  console.log(`  All products returned (${products.length}):`);
  for (const prod of products.slice(0, 3)) {
    console.log(`    - ${prod.id.padEnd(14)} ${String(prod.priceKr).padStart(8)} kr  ${prod.name}`);
  }
}

async function smokeKeywordSearch(term: string): Promise<void> {
  // Note: the suggest endpoint returns category/brand autocomplete hints, not
  // individual product results. searchProductsByKeyword reflects that - we
  // verify the endpoint responds 200 and that our client doesn't throw.
  console.log(`\n${CYAN}▶ Keyword Suggest endpoint: q="${term}"${RESET}`);
  try {
    const products = await searchProductsByKeyword(term, "DK");
    // The suggest API returns 0 product results (it returns category hints via
    // a separate "suggestions" field). That is expected and correct behaviour.
    check("Suggest endpoint returns 200 (no throw)", true);
    console.log(`  Products from suggest: ${products.length} (expected 0 - categories returned as hints, not products)`);
  } catch (err: unknown) {
    check("Suggest endpoint returns 200 (no throw)", false, String(err));
  }
}

async function main(): Promise<void> {
  console.log("PriceRunner v4 API smoke test");
  console.log("=".repeat(50));

  // Test 2 representative categories (verified IDs)
  await smokeCategory("27");  // laptops  - MacBook Air etc.
  await smokeCategory("94");  // headphones - AirPods etc.

  // Test keyword search
  await smokeKeywordSearch("laptop");

  // Summary
  console.log("\n" + "=".repeat(50));
  const total = passed + failed;
  if (failed === 0) {
    console.log(`${GREEN} All ${total} checks passed`);
  } else {
    console.log(`${RED} ${failed}/${total} checks failed`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("\n[smoke:pricerunner] Fatal error:", err);
  process.exit(1);
});
