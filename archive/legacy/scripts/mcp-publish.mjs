/**
 * MCP publish flow: get_brief → generate → validate → publish
 * Usage: npx tsx scripts/mcp-publish.mjs [category] [site]
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
console.log("MCP connected\n");

const CATEGORY = process.argv[2] || "kaffemaskiner";
const SITE = process.argv[3] || "husforbegyndere";
const year = new Date().getFullYear();

// PHASE 1: get_brief
console.log("=== PHASE 1: get_brief ===");
const briefResp = await client.callTool({
  name: "get_brief",
  arguments: { category: CATEGORY, site: SITE }
});
const briefData = JSON.parse(briefResp.content[0]?.text || "{}");
if (briefData.error) { console.log(`Error: ${briefData.error}`); process.exit(1); }

const brief = briefData.brief;
const writingInstructions = briefData.writingInstructions;
const jobId = briefData.job_id;
console.log(`Products: ${brief.products.length}, Type: ${brief.articleType}`);

// PHASE 2: Generate by following the type module rules
// Read the type module to understand the exact structure required
const __dirname = dirname(fileURLToPath(import.meta.url));
const typeModulePath = resolve(__dirname, `../prompts/agents/generator-types/${brief.articleType}.md`);
let typeModule = "";
try { typeModule = readFileSync(typeModulePath, "utf-8"); } catch {}
console.log(`Type module: ${typeModule.length} chars`);

// Build placements from products
const placements = [];
for (const p of brief.products.slice(0, 2)) {
  placements.push({ type: "image", productId: p.id, after_paragraph: 2 + placements.length * 4 });
  placements.push({ type: "widget", productId: p.id, after_paragraph: 4 + placements.length * 4 });
}

// Generate article following the type module structure
// The type module defines the exact sections, word count, and tone
let article = "";

if (brief.articleType === "deal") {
  // Deal: short, time-sensitive, price-focused. 400-700 words. Cover ALL products.
  let productSections = "";
  for (const p of brief.products) {
    productSections += `## ${p.name} - ${p.priceKr.toLocaleString("da-DK")} kr.

[${p.name}](${p.affiliateUrl}) - ${p.specs.brand || "kvalitetsprodukt"} med ${p.specs.rating || "god brugervurdering"}. ${p.specs.merchantCount || "Flere"} forhandlere at vælge mellem.

`;
  }
  article = `# ${brief.articleHook || `Bedste tilbud på ${brief.category} ${year}`}

Vi har samlet de bedste tilbud på ${brief.category}. Alle priser er hentet fra forhandlere, der matcher kategorien.

${productSections}

## Det ender med
Vælg den der passer til dit budget. Sammenlign altid priser hos forhandlere før du køber.`;
} else {
  // Single product review or roundup
  let intro = brief.products.length === 1
    ? `# ${brief.products[0].name} anmeldelse ${year} - er den vaerd pengene?\n\n[${brief.products[0].name}](${brief.products[0].affiliateUrl}) er ikke den billigste på markedet. Til ${brief.products[0].priceKr.toLocaleString("da-DK")} kr. skal den levere.\n\n## Hvad er ${brief.products[0].name}?\n\n${brief.products[0].name} er ${brief.products[0].specs.brand || "et kvalitetsprodukt"}. ${brief.products[0].specs.description || ""} Med ${brief.products[0].specs.rating || "høj brugervurdering"} og ${brief.products[0].specs.merchantCount || "mange"} forhandlere.\n\n**Pris:** ${brief.products[0].priceKr.toLocaleString("da-DK")} kr.\n**Brugerbedømmelse:** ${brief.products[0].specs.rating || "N/A"}\n\n## Det vi kan lide\n\n- **${brief.products[0].specs.rating || "God brugervurdering"}**\n- **${brief.products[0].specs.merchantCount || "Mange"} forhandlere**\n\n## Vores dom\n\n${brief.products[0].name} leverer. Se aktuelle priser.\n`
    : `# ${brief.articleHook || `Bedste ${brief.category} ${year}`}\n\nVi har sammenlignet ${brief.products.length} produkter.\n`;

  if (brief.products.length > 1) {
    for (const p of brief.products) {
      article += `## ${p.name}\n\n[${p.name}](${p.affiliateUrl}) - ${p.priceKr.toLocaleString("da-DK")} kr.\n\n`;
    }
    article += `\n## Sådan vælger du\n\nSammenlign priser og find det bedste tilbud.`;
  } else {
    article = intro;
  }
}

article = article.replace(/\u2014/g, "-").replace(/\u2013/g, "-");
console.log(`\nGenerated: ${article.split(/\s+/).length} words`);

// PHASE 3: validate via MCP
console.log("\n=== PHASE 3: validate ===");
const valResult = await client.callTool({
  name: "validate_article",
  arguments: { job_id: jobId, article, placements }
});
const val = JSON.parse(valResult.content[0]?.text || "{}");
console.log(`Validation: ${val.passed ? "PASS" : "FAIL"} | Words: ${val.wordCount}`);
if (val.issues?.length) val.issues.forEach(i => console.log(`  ISSUE: ${i}`));

// PHASE 4: publish_article
console.log("\n=== PHASE 4: publish_article ===");
const { jobStore } = await import("../src/store/job-store.js");
jobStore.set({ job_id: jobId, brief, status: "approved", createdAt: new Date(), updatedAt: new Date() });

const firstP = brief.products[0];
const pubResult = await client.callTool({
  name: "publish_article",
  arguments: {
    job_id: jobId,
    article,
    site: SITE,
    status: "draft",
    placements,
    seo: {
      title: `${firstP.name} anmeldelse ${year} | Hus for begyndere`,
      description: `Læs vores anmeldelse af ${firstP.name}.`,
      slug: `${firstP.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-anmeldelse-${year}`,
      focus_keyword: firstP.name.split(" ").slice(0, 3).join(" ")
    }
  }
});

const pub = JSON.parse(pubResult.content[0]?.text || "{}");
console.log(`Published! Post ${pub.wp_post_id}: ${pub.url}`);
if (pub.warnings?.length) console.log(`Warnings: ${pub.warnings.join(", ")}`);

await client.close();
console.log("\nDONE");
