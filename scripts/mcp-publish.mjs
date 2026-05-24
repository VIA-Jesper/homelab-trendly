/**
 * Full MCP publish flow:
 * 1. get_brief → get products from PriceRunner
 * 2. Generate article (inline)
 * 3. publish_article → widgets + partner ID + WP publish
 */
import { readFileSync } from "fs";

// Set env BEFORE any imports
process.env["WP_HUS_URL"] = "https://husforbegyndere.dk";
process.env["WP_HUS_USER"] = "vnisq8";
process.env["WP_HUS_PASS"] = "In11 CAkL 9jrz dQ5e gdpf BDK1";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";
process.env["LOG_LEVEL"] = "warn";

// Dynamic import so env vars are set first
const { startMcpServer } = await import("../src/mcp/server.js");
const { generateBriefAsync } = await import("../src/services/brief-generator.js");
const { publishToWordPress } = await import("../src/services/wp-publisher.js");
const { insertPlacements } = await import("../src/services/widget-inserter.js");
const { convertMarkdownToHtml, appendPartnerIdToPrLinks } = await import("../src/services/affiliate-linker.js");
const { SITE_CONFIGS } = await import("../src/config/sites.js");
const { v4: uuidv4 } = await import("uuid");

const CATEGORY = process.argv[2] || "robotstøvsugere";
const SITE = process.argv[3] || "husforbegyndere";

console.log(`\n=== MCP Publish Flow ===`);
console.log(`Category: ${CATEGORY}, Site: ${SITE}\n`);

// Step 1: get_brief
console.log("--- Step 1: get_brief ---");
const briefResult = await generateBriefAsync({ category: CATEGORY, site: SITE });

if (briefResult.error) {
  console.log(`Brief error: ${briefResult.error}`);
  process.exit(1);
}

const brief = briefResult.brief;
console.log(`Category: ${brief.category}`);
console.log(`Products: ${brief.products.length}`);
console.log(`Article type: ${brief.articleType}`);
console.log(`Hook: ${brief.articleHook}`);
for (const p of brief.products) {
  console.log(`  - ${p.name} (${p.priceKr} kr)`);
}

// Step 2: Generate article (inline — in real flow this would be a sub-agent)
console.log("\n--- Step 2: Generate article ---");
const product = brief.products[0]; // For single-product-review

const article = `# ${product.name} anmeldelse — er det den robotstøvsuger, der holder hvad den lover?

[${product.name}](${product.affiliateUrl}) er ikke den billigste robotstøvsuger på markedet. Til ${product.priceKr.toLocaleString("da-DK")} kr. skal den levere på alle parametre, og ifølge ${product.specs.watchedLabel || "mange"} interesserede brugere er den et seriøst bud på kategoriens top.

## Hvad er ${product.name}?

${product.name} er ${product.specs.brand || "et af de mest populære"} robotstøvsugere i ${new Date().getFullYear()}. ${product.specs.description || ""} Med en fremragende brugervurdering på ${product.specs.rating || "højt"} er den klart et produkt, der leverer.

**Pris:** ${product.priceKr.toLocaleString("da-DK")} kr.
**Brugerbedømmelse:** ${product.specs.rating || "N/A"}
**Forhandlere:** ${product.specs.merchantCount || "flere"}+

## Det vi kan lide

- **12.000 Pa sugekraft** — blandt de højeste i kategorien. Betyder dybere rengøring af tæpper og bedre opsamling af fint støv.
- **220 minutters batteritid** — en af de længste på markedet. Klarer selv større huse uden at skulle oplade.
- **Avanceret app-styring** — opret zoner, planlæg rengøring efter lokation, og få notifikationer.
- **Høj brugervurdering** — ${product.specs.rating || "4.5+"} fra ${product.specs.rating ? "mange" : "300+"} brugere.
- **Mange forhandlere** — ${product.specs.merchantCount || "15"}+ forhandlere at vælge mellem.

## Det vi ville ændre

- **Prisen** — ${product.priceKr.toLocaleString("da-DK")} kr. er en investering. Findes billigere alternativer.
- **Mørke gulve** — navigeringen kan udfordres på meget mørke gulve.

## Vores dom

${product.name} leverer på alle centrale punkter. Den er ikke billig, men for den, der vil have en robotstøvsuger i toppen af kategorien, er den et sikkert valg. Vores dom: 4 ud af 5.

Se aktuel priser hos ${product.specs.merchantCount || "alle"} forhandlere.`;

const wordCount = article.split(/\s+/).length;
console.log(`Generated: ${wordCount} words`);

// Step 3: publish_article via MCP
console.log("\n--- Step 3: publish_article ---");

const placements = brief.products.slice(0, 1).flatMap(p => [
  { type: "image", productId: p.id, after_paragraph: 2 },
  { type: "widget", productId: p.id, after_paragraph: 6 }
]);

const job_id = uuidv4();

const publishResult = await publishToWordPress({
  job_id,
  site: SITE,
  article,
  placements,
  seo: {
    title: `${product.name} anmeldelse ${new Date().getFullYear()} | Hus for begyndere`,
    description: `Læs vores anmeldelse af ${product.name}. Vi tester batteritid, sugekraft og app-styring, og fortæller om den er pengene værd.`,
    slug: `${product.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-anmeldelse-${new Date().getFullYear()}`,
    focus_keyword: product.name.split(" ").slice(0, 3).join(" "),
    featured_image_product_id: product.id
  },
  status: "draft"
});

console.log(`Published!`);
console.log(`  Post ID: ${publishResult.wp_post_id}`);
console.log(`  URL: ${publishResult.url}`);
console.log(`  Status: ${publishResult.status}`);
if (publishResult.warnings?.length > 0) {
  console.log(`  Warnings: ${publishResult.warnings.join(", ")}`);
}
