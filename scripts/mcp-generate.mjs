/**
 * Step 1: get_brief via MCP
 * Step 2: Output the full generation prompt for OWL to use
 * Step 3: OWL writes the article following the instructions
 * Step 4: validate + publish via MCP
 *
 * Usage: npx tsx scripts/mcp-generate.mjs [category] [site]
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

process.env["WP_HUS_URL"] = "https://husforbegyndere.dk";
process.env["WP_HUS_USER"] = "vnisq8";
process.env["WP_HUS_PASS"] = "In11 CAkL 9jrz dQ5e gdpf BDK1";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";
process.env["LOG_LEVEL"] = "warn";

const { startMcpServer } = await import("../src/mcp/server.js");
await startMcpServer();
await new Promise(r => setTimeout(r, 1000));

const client = new Client({ name: "owl", version: "1.0" });
const transport = new StreamableHTTPClientTransport(new URL("http://localhost:3001/mcp"));
await client.connect(transport);

const CATEGORY = process.argv[2] || "kaffemaskiner";
const SITE = process.argv[3] || "husforbegyndere";
const year = new Date().getFullYear();

// get_brief
const briefResp = await client.callTool({
  name: "get_brief",
  arguments: { category: CATEGORY, site: SITE }
});
const briefData = JSON.parse(briefResp.content[0]?.text || "{}");
if (briefData.error) { console.log(`Error: ${briefData.error}`); process.exit(1); }

const brief = briefData.brief;
const writingInstructions = briefData.writingInstructions;
const jobId = briefData.job_id;

// Output the full generation prompt
console.log("=== BRIEF DATA ===");
console.log(JSON.stringify({
  jobId,
  category: brief.category,
  articleType: brief.articleType,
  articleHook: brief.articleHook,
  products: brief.products.map(p => ({
    id: p.id,
    name: p.name,
    priceKr: p.priceKr,
    brand: p.specs.brand,
    rating: p.specs.rating,
    watchedLabel: p.specs.watchedLabel,
    merchantCount: p.specs.merchantCount,
    description: p.specs.description,
    affiliateUrl: p.affiliateUrl,
    imageUrl: brief.images.find(i => i.productId === p.id)?.url
  })),
  writingInstructions
}, null, 2));

await client.close();
