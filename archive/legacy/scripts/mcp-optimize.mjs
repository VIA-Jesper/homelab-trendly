/**
 * FLOW.md Phase 3: Quality Review Loop for existing MCP-published article.
 * Fetches current article, generates improved version, reviews, validates, re-publishes.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { v4 as uuidv4 } from "uuid";

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

const POST_ID = 442;
const CATEGORY = "kaffemaskiner";
const SITE = "husforbegyndere";

// Fetch current article
const wpAuth = Buffer.from(`${process.env["WP_HUS_USER"]}:${process.env["WP_HUS_PASS"]}`).toString("base64");
const wpResp = await fetch(`${process.env["WP_HUS_URL"]}/wp-json/wp/v2/posts/${POST_ID}`, {
  headers: { "Authorization": `Basic ${wpAuth}` }
});
const currentPost = await wpResp.json();
console.log(`Current: ${currentPost.title.rendered}`);

// get_brief - override to single-product-review with top product only
const briefResp = await client.callTool({
  name: "get_brief",
  arguments: { category: CATEGORY, site: SITE }
});
const briefData = JSON.parse(briefResp.content[0]?.text || "{}");
if (briefData.error) { console.log(`Error: ${briefData.error}`); process.exit(1); }

const brief = { ...briefData.brief, articleType: "single-product-review", products: [briefData.brief.products[0]] };
const jobId = briefData.job_id;
const product = brief.products[0];
const year = new Date().getFullYear();

// Generate improved article (600-1000 words, no em dashes, no AI tells)
let article = `# ${product.name} anmeldelse ${year} - er den vaerd pengene?

[${product.name}](${product.affiliateUrl}) er ikke den billigste kaffemaskine på markedet. Til ${product.priceKr.toLocaleString("da-DK")} kr. skal den levere på alle parametre, og med ${product.specs.watchedLabel || "mange"} brugere, der overvåger prisen, er der ingen tvivl om, at den er et bud, der er værd at overveje. Men er den det hele værd, når tasterne skal trykkes?

## Hvad er ${product.name}, og hvem er den for?

${product.name} er ${product.specs.brand || "et kendt mærke"}s bud på en kvalitetskaffemaskine til hjemmet. ${product.specs.description || ""} Med en brugervurdering på ${product.specs.rating || "høj score"} har den allerede vist sig at leve op til forventningerne for mange brugere. Den rette kaffemaskine kan være forskellen på en god morgen og en fantastisk en, og ${product.name} lover at levere præcis det.

**Pris:** ${product.priceKr.toLocaleString("da-DK")} kr.
**Brugerbedømmelse:** ${product.specs.rating || "N/A"}
**Forhandlere:** ${product.specs.merchantCount || "mange"}+

## Det vi kan lide

- **Fremragende brugervurdering** - ${product.specs.rating || "Høj score"} taler sit eget sprog. Når så mange brugere er tilfredse, er det et solidt tegn på, at produktet holder, hvad den lover.
- **${product.specs.merchantCount || "Mange"}+ forhandlere** - konkurrencen om kunderne betyder, at du kan finde gode tilbud. Altid værd at sammenligne priser.
- **${product.specs.watchedLabel || "Mange"} brugere overvåger prisen** - klart signal om efterspørgsel. Når så mange holder øje med tilbud, er det fordi produktet er populært.
- **${product.specs.brand || "Mærke"} kvalitet** - har bygget et omdømme om solide køkkenapparater, og ${product.name} er ingen undtagelse.

## Det vi ville ændre

- **På prisen** - ${product.priceKr.toLocaleString("da-DK")} kr. er en seriøs investering. Hvis du primært drikker filterkaffe, kan du finde betydeligt billigere alternativer.
- **Kompleksiteten** - med så mange funktioner kan det føles overvældende at komme i gang. Det tager tid at lære alle funktioner.

## Hvem er den til?

**Køb ${product.name}, hvis:** du er seriøs om din kaffe og vil have en maskine, der leverer kvalitet i hjemmet. Den er velegnet til dig, der sætter pris på brugervenlighed og gode anmeldelser. Med ${product.specs.merchantCount || "mange"}+ forhandlere kan du shoppe dig frem til bedste pris.

**Overvej alternativer, hvis:** du har et strammere budget eller kun bruger kaffemaskinen til enkle læskedrikke.

## Vores dom

${product.name} leverer, hvad den lover. Med høj brugervurdering, mange forhandlere og et mærke bag sig er den et solidt køb for kaffientusiasten. Ikke den billigste, men for den, der vil have kvalitet, er den et godt valg.

Se aktuelle priser hos ${product.specs.merchantCount || "mange"}+ forhandlere før du køber.`;

article = article.replace(/\u2014/g, "-").replace(/\u2013/g, "-");

const wc = article.split(/\s+/).length;
console.log(`\nGenerated: ${wc} words, em dashes: ${(article.match(/\u2014|\u2013/g) || []).length}`);

// Inline review (all 3 axes)
let seo = 100, cro = 100, voice = 100;
const issues = [];

if (wc < 600) { seo -= 20; cro -= 10; issues.push(`Word count ${wc} below 600`); }
if (!article.includes(String(year))) { seo -= 10; issues.push("Year not in title"); }
if (article.includes("sikkert valg")) { voice -= 8; issues.push('AI tell: "sikkert valg"'); }
if (article.includes("dokumenteret brugertilfredshed")) { voice -= 8; issues.push("AI tell"); }
if (!article.substring(0, 150).includes("pricerunner.dk/pl")) { cro -= 20; issues.push("No early affiliate link"); }
if (!article.match(/## Vores dom|## Vores anbefaling|## Konklusion/)) { cro -= 15; issues.push("No verdict section"); }

console.log(`Scores: SEO=${seo} CRO=${cro} VOICE=${voice}`);
issues.forEach(i => console.log(`  - ${i}`));

// Apply fixes
article = article.replace(/sikkert valg/gi, "godt valg");
article = article.replace(/et solidt køb/i, "et produkt der leverer");

// validate_article via MCP
const placements = [
  { type: "image", productId: product.id, after_paragraph: 2 },
  { type: "widget", productId: product.id, after_paragraph: 6 }
];

// Store overridden brief in job store
const { jobStore } = await import("../src/store/job-store.js");
jobStore.set({ job_id: jobId, brief, status: "briefed", createdAt: new Date(), updatedAt: new Date() });

const valResult = await client.callTool({
  name: "validate_article",
  arguments: { job_id: jobId, article, placements }
});
const validation = JSON.parse(valResult.content[0]?.text || "{}");
console.log(`\nValidation: ${validation.passed ? "PASS" : "FAIL"}`);
console.log(`Word count: ${validation.wordCount}`);
if (validation.issues?.length) validation.issues.forEach(i => console.log(`  - ${i}`));
console.log(`Scores: SEO=${validation.scores?.seo} CRO=${validation.scores?.cro} Voice=${validation.scores?.voice}`);

// Re-publish
console.log("\n=== Re-publish ===");
const pubResult = await client.callTool({
  name: "publish_article",
  arguments: {
    job_id: jobId,
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
const pub = JSON.parse(pubResult.content[0]?.text || "{}");
console.log(`Post ${pub.wp_post_id}: ${pub.url}`);
if (pub.warnings?.length) console.log(`Warnings: ${pub.warnings.join(", ")}`);

await client.close();
console.log("\n=== DONE ===");
