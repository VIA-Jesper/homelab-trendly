import { fetchProductsByCategoryId } from "../src/scraper/pricerunner-client.js";

const RENOVATION_CATEGORIES: Array<{ id: string; name: string }> = [
  { id: "1300", name: "Maling (Paint)" },
  { id: "1302", name: "Fliser-Klinker (Tiles)" },
  { id: "1304", name: "Gulve (Floors)" },
  { id: "1306", name: "Tapeter (Wallpaper)" },
];

async function main() {
  console.log("PriceRunner v4 - Renovering & Byggeri leaf categories");
  console.log("=".repeat(60));

  for (const cat of RENOVATION_CATEGORIES) {
    console.log(`\n▶ Category ${cat.id}: ${cat.name}`);
    try {
      const products = await fetchProductsByCategoryId(cat.id, "DK", 5);
      if (products.length === 0) {
        console.log("  ✗ No products returned");
        continue;
      }
      console.log(`  ✓ ${products.length} products`);
      for (const p of products) {
        const price = p.priceKr > 0 ? `${p.priceKr} kr` : "(no price)";
        const retailer = p.retailer ?? "?";
        console.log(`  - ${p.id.padEnd(20)} ${price.padEnd(12)} ${p.name.substring(0, 60)}`);
        console.log(`    retailer: ${retailer} | image: ${p.imageUrl ? "✓" : "✗"} | affiliate: ${p.affiliateUrl ? "✓" : "✗"}`);
      }
    } catch (err: unknown) {
      console.log(`  ✗ ERROR: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

main().catch(console.error);
