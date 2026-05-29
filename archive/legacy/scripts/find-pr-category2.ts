/**
 * Find DIY PriceRunner category IDs by probing known URL patterns.
 */
import axios from "axios";

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36";

// First: dump raw suggest response to see full URL field
const res = await axios.get(
  "https://www.pricerunner.dk/dk/api/instant-search-edge-rest/public/search/suggest/DK",
  { params: { q: "boremaskine" }, headers: { "User-Agent": UA, Accept: "application/json" }, timeout: 10_000 }
);
console.log("Raw suggest (first 3):");
(res.data.suggestions ?? []).slice(0,3).forEach((h: Record<string, unknown>) => console.log(JSON.stringify(h)));

// Second: probe a wider range of DIY-likely category IDs
// PriceRunner tool/home improvement IDs are likely in 1100-1700 range
const probeIds = [
  "1100","1200","1230","1240","1250","1260","1270","1280","1290",
  "1300","1310","1320","1330","1340","1350","1360","1370","1380","1390",
  "1400","1410","1420","1430","1440","1450","1460","1470","1480","1490",
  "1500","1510","1520","1530","1540","1550","1560","1570","1580","1590",
  "1600","1610","1620","1630","1640","1650","1660","1670","1680","1690",
  "1700","1710","1720","1730","1740","1750","1760","1770","1780","1790",
];

console.log("\nProbing range 1100-1790 (10-ID batches)...\n");

for (const catId of probeIds) {
  try {
    const r = await axios.get(
      `https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK/${catId}`,
      {
        params: { size: 2, sorting: "POPULARITY", device: "desktop" },
        headers: { "User-Agent": UA, Accept: "application/json" },
        timeout: 6_000,
      }
    );
    const products: Array<{ name?: string }> = r.data?.products ?? r.data?.results ?? [];
    if (products.length > 0) {
      const first = products[0]?.name ?? "?";
      // Try to infer category from product name
      const isDIY = /bor|sav|slib|hammer|maler|skrue|højtryk|hæk|tryk|klip|grav|svejse|rulle|kæde|rydde|tæppe|sten/i.test(first);
      const marker = isDIY ? " ⬅ TOOLS?" : "";
      console.log(`  ${catId}: ${first}${marker}`);
    }
  } catch {
    // ignore 404/403
  }
  await new Promise((r) => setTimeout(r, 300));
}
