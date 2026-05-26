/**
 * Quick utility: discover PriceRunner category IDs by keyword search.
 * Usage: npx tsx scripts/find-pr-category.ts <keyword>
 * Example: npx tsx scripts/find-pr-category.ts boremaskine
 */
import axios from "axios";

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36";

interface SuggestHit {
  id?: string;
  name?: string;
  type?: string;
  url?: string;
}

interface SuggestResponse {
  suggestions?: SuggestHit[];
}

const term = process.argv[2] ?? "boremaskine";
console.log(`\nSearching PriceRunner DK for: "${term}"\n`);

const res = await axios.get<SuggestResponse>(
  "https://www.pricerunner.dk/dk/api/instant-search-edge-rest/public/search/suggest/DK",
  {
    params: { q: term },
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
    timeout: 10_000,
  }
);

const hits = res.data.suggestions ?? [];
if (hits.length === 0) {
  console.log("No suggestions returned.");
} else {
  console.log("TYPE         ID        NAME");
  console.log("─".repeat(70));
  hits.forEach((h) => {
    // Extract numeric ID from URL if not present directly
    const idFromUrl = h.url ? /\/(\d+)$/.exec(h.url)?.[1] ?? h.url.split("/").slice(-1)[0] : "-";
    const id = h.id ?? idFromUrl ?? "-";
    console.log(`${(h.type ?? "?").padEnd(12)} ${id.padEnd(10)} ${h.name ?? "-"}`);
  });
}

// Also try fetching top products from some guessed DIY category IDs
const diyCandidates = ["4", "204", "391", "392", "393", "394", "395", "396", "397", "398", "399", "400"];
console.log("\n\nProbing candidate category IDs for DIY products...\n");
for (const catId of diyCandidates) {
  try {
    const catRes = await axios.get(
      `https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK/${catId}`,
      {
        params: { size: 3, sorting: "POPULARITY", device: "desktop" },
        headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
        timeout: 8_000,
      }
    );
    const products = catRes.data?.products ?? catRes.data?.results ?? [];
    if (products.length > 0) {
      const names = products.slice(0, 2).map((p: { name?: string }) => p.name ?? "?").join(", ");
      console.log(`  CatID ${catId.padEnd(6)}: ${names}`);
    }
  } catch {
    // skip
  }
  await new Promise((r) => setTimeout(r, 600));
}
