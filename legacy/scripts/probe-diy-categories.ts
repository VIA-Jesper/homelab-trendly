/**
 * Probe specific DIY PriceRunner category IDs to find the best one for article generation.
 */
import axios from "axios";

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36";

interface V4Product {
  id: string;
  name: string;
  lowestPrice?: { amount: string };
  rank?: { rank: number };
  ribbon?: { type: string; value?: string };
  previewMerchants?: { count: number };
  brand?: { name: string };
}

async function fetchCat(catId: string, label: string) {
  try {
    const r = await axios.get(
      `https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK/${catId}`,
      {
        params: { size: 8, sorting: "POPULARITY", device: "desktop" },
        headers: { "User-Agent": UA, Accept: "application/json" },
        timeout: 10_000,
      }
    );
    const products: V4Product[] = r.data?.products ?? r.data?.results ?? [];
    console.log(`\n═══ ${label} (ID: ${catId}) — ${products.length} products ═══`);
    products.slice(0, 6).forEach((p, i) => {
      const price = p.lowestPrice?.amount ? `${parseFloat(p.lowestPrice.amount).toLocaleString("da-DK")} kr.` : "?";
      const rank = p.rank?.rank ? `#${p.rank.rank}` : "   ";
      const watched = p.ribbon?.type === "WATCHED" ? ` 👁 ${p.ribbon.value ?? "?"}` : "";
      const merchants = p.previewMerchants?.count ? ` / ${p.previewMerchants.count} shops` : "";
      const brand = p.brand?.name ? `[${p.brand.name}] ` : "";
      console.log(`  ${rank} ${brand}${p.name} — ${price}${merchants}${watched}`);
    });
    return products.length;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.log(`\n${label} (ID: ${catId}) — ERROR: ${msg}`);
    return 0;
  }
}

// DIY / Home improvement categories to probe
const categories = [
  { id: "1258", label: "Bore- & Skruemaskiner (drills)" },
  { id: "1260", label: "Rundsave / Kapsave (saws)" },
  { id: "1262", label: "Candidate 1262" },
  { id: "1264", label: "Candidate 1264" },
  { id: "1266", label: "Candidate 1266" },
  { id: "1268", label: "Candidate 1268" },
  { id: "1270", label: "Candidate 1270" },
  { id: "1272", label: "Candidate 1272" },
  { id: "1274", label: "Candidate 1274" },
  { id: "1276", label: "Candidate 1276" },
  { id: "1278", label: "Candidate 1278" },
];

// Also try some known home/garden IDs from the suggest API results
const moreCategories = [
  { id: "1300", label: "Building materials (1300)" },
  { id: "1302", label: "Candidate 1302" },
  { id: "1304", label: "Candidate 1304" },
  { id: "1306", label: "Candidate 1306" },
  { id: "1308", label: "Candidate 1308" },
];

for (const cat of [...categories, ...moreCategories]) {
  await fetchCat(cat.id, cat.label);
  await new Promise((r) => setTimeout(r, 500));
}
