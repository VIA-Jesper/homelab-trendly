/**
 * MCP Client for trendly pipeline.
 * Usage: npx tsx scripts/mcp-client.mjs [category] [site]
 *
 * Full flow: get_brief -> generate -> publish_article (via MCP)
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { v4 as uuidv4 } from "uuid";

// Set env BEFORE imports
process.env["WP_HUS_URL"] = "https://husforbegyndere.dk";
process.env["WP_HUS_USER"] = "vnisq8";
process.env["WP_HUS_PASS"] = "In11 CAkL 9jrz dQ5e gdpf BDK1";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";
process.env["LOG_LEVEL"] = "warn";

// Dynamic imports
const { startMcpServer } = await import("../src/mcp/server.js");
await startMcpServer();
await new Promise(r => setTimeout(r, 1000));

const client = new Client({ name: "owl", version: "1.0" });
const transport = new StreamableHTTPClientTransport(new URL("http://localhost:3001/mcp"));
await client.connect(transport);
console.log("MCP connected");

const CATEGORY = process.argv[2] || "kaffemaskiner";
const SITE = process.argv[3] || "husforbegyndere";

// Step 1: get_brief
console.log(`\n=== Step 1: get_brief (${CATEGORY}) ===`);
const briefResult = await client.callTool({
  name: "get_brief",
  arguments: { category: CATEGORY, site: SITE }
});
const brief = JSON.parse(briefResult.content[0]?.text || "{}");

if (brief.error) {
  console.log(`Error: ${brief.error}`);
  await client.close();
  process.exit(1);
}

console.log(`Products: ${brief.brief.products.length}, Type: ${brief.brief.articleType}`);
for (const p of brief.brief.products) {
  console.log(`  - ${p.name} (${p.priceKr} kr)`);
}

// Step 2: Build article (no em dashes)
console.log("\n=== Step 2: Generate ===");
const product = brief.brief.products[0];
const year = new Date().getFullYear();

let article = `# ${product.name} anmeldelse - er det vaerd pengene?

[${product.name}](${product.affiliateUrl}) er et af de mest populære produkter i sin kategori. Til ${product.priceKr.toLocaleString("da-DK")} kr. skal den levere på alle parametre, og ifølge ${product.specs.watchedLabel || "mange"} brugere er den et seriøst bud.

## Hvad er ${product.name}?

${product.name} er ${product.specs.brand || "et kvalitetsprodukt"} med ${product.specs.rating || "høj brugervurdering"}. ${product.specs.description || ""} Med ${product.specs.merchantCount || "flere"} forhandlere er der gode muligheder for at finde et tilbud.

**Pris:** ${product.priceKr.toLocaleString("da-DK")} kr.
**Brugerbedømmelse:** ${product.specs.rating || "N/A"}
**Forhandlere:** ${product.specs.merchantCount || "flere"}+

## Det vi kan lide

- **Høj kvalitet** - ${product.specs.rating || "God"} brugervurdering.
- **Mange forhandlere** - ${product.specs.merchantCount || "10"}+ forhandlere.
- **Populært valg** - ${product.specs.watchedLabel || "Mange"} brugere følger med.

## Det vi ville ændre

- **Prisen** - ${product.priceKr.toLocaleString("da-DK")} kr. er en investering.

## Vores dom

${product.name} leverer på alle centrale punkter. Solid kvalitet og høj brugervurdering gør det til et sikkert valg.

Se aktuelle priser på ${product.name}.`;

// Kill any remaining em/en dashes
article = article.replace(/\u2014/g, "-").replace(/\u2013/g, "-");

console.log(`Words: ${article.split(/\s+/).length}, Em dashes: ${(article.match(/\u2014|\u2013/g) || []).length}`);

// Build placements
const placements = [
  { type: "image", productId: product.id, after_paragraph: 2 },
  { type: "widget", productId: product.id, after_paragraph: 6 }
];

// Step 3: publish_article via MCP
console.log("\n=== Step 3: publish_article ===");
const result = await client.callTool({
  name: "publish_article",
  arguments: {
    job_id: brief.job_id || uuidv4(),
    article,
    site: SITE,
    status: "draft",
    placements,
    seo: {
      title: `${product.name} anmeldelse ${year} | Hus for begyndere`,
      description: `Læs vores anmeldelse af ${product.name}. Vi tester kvalitet og fortæller om den er pengene værd.`,
      slug: `${product.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-anmeldelse-${year}`,
      focus_keyword: product.name.split(" ").slice(0, 3).join(" "),
      featured_image_product_id: product.id
    }
  }
});

const pubResult = JSON.parse(result.content[0]?.text || "{}");
console.log(`Status: ${pubResult.status}`);
console.log(`Post ID: ${pubResult.wp_post_id}`);
console.log(`URL: ${pubResult.url}`);
if (pubResult.warnings?.length) console.log(`Warnings: ${pubResult.warnings.join(", ")}`);

await client.close();
console.log("\n=== DONE ===");
