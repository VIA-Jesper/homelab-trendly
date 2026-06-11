/**
 * Quick smoke test for get_brief + validate_article without going through HTTP.
 * Run with: npx tsx scripts/test-mcp-tools.ts
 */
import { generateBriefAsync } from "../src/services/brief-generator.js";
import { validateArticleFull } from "../src/services/validator.js";

const GREEN = "\x1b[32m✓\x1b[0m";
const RED   = "\x1b[31m✗\x1b[0m";

function check(label: string, ok: boolean, detail?: string): void {
  if (ok) console.log(`  ${GREEN} ${label}`);
  else     console.log(`  ${RED} ${label}${detail ? ` - ${detail}` : ""}`);
}

async function main(): Promise<void> {
  // ── get_brief ─────────────────────────────────────────────────────────────
  console.log("\n▶ generateBriefAsync('robotstovsugere', techblog)");
  const brief = await generateBriefAsync("robotstovsugere", undefined, "techblog");
  if ("error" in brief) {
    console.error("  ERROR:", JSON.stringify(brief));
    process.exit(1);
  }

  check("category is robotstovsugere", brief.category === "robotstovsugere");
  check("articleType is set", typeof brief.articleType === "string");
  check("5 products returned", brief.products.length === 5,
    `got ${brief.products.length}`);
  check("products have prices", brief.products.every((p) => p.priceKr > 0));
  check("writing_rules present", !!brief.writing_rules);

  console.log(`\n  Products:`);
  brief.products.forEach((p) => console.log(`    - ${p.name} (${p.priceKr} kr)`));

  // ── validate_article ───────────────────────────────────────────────────────
  console.log("\n▶ validateArticleFull");
  const p0 = brief.products[0];
  const p1 = brief.products[1];
  const article = [
    `## De bedste robotstovsugere 2026`,
    ``,
    `Robotstovsugere er blevet uundvaerlige i moderne hjem. Vi har testet og sammenlignet de bedste modeller fra de stoerste maerker for at hjaelpe dig med at traffe det rigtige valg. Laes vores guide og find den bedste robotstovsuger til dit hjem og budget.`,
    ``,
    `### ${p0.name} - Vores Topvalg`,
    ``,
    `${p0.name} til ${p0.priceKr} kr er en fremraende robotstovsuger med kraftfuld sugeevne og intelligent navigation. Vi anbefaler den til de fleste hjem.`,
    ``,
    `**Fordele:** kraftfuld sugeevne, automatisk tomning, lang batteritid`,
    `**Ulemper:** hoj pris`,
    ``,
    `### ${p1.name}`,
    ``,
    `${p1.name} er ogsaa et godt valg til en rimelig pris. Den passer perfekt til mellemstore hjem.`,
    ``,
    `## Konklusion`,
    ``,
    `Vi anbefaler ${p0.name} som det bedste valg for de fleste. Husk at sammenligne priser foer koeb.`,
    ``,
    `*Vi modtager provision ved koeb via vores affiliate-links.*`,
  ].join("\n");

  const placements = [
    { type: "widget" as const, position: "after_intro", content: "<div>widget</div>" },
  ];

  const result = await validateArticleFull(article, brief, placements);

  check("passed is boolean", typeof result.passed === "boolean");
  check("wordCount > 0", result.wordCount > 0, `got ${result.wordCount}`);
  check("issues is array", Array.isArray(result.issues));
  check("scores.seo >= 0", result.scores.seo >= 0);
  check("scores.voice >= 0", result.scores.voice >= 0);
  check("scores.cro >= 0", result.scores.cro >= 0);

  console.log(`\n  Result:`);
  console.log(`    passed:    ${result.passed}`);
  console.log(`    wordCount: ${result.wordCount}`);
  console.log(`    scores:    ${JSON.stringify(result.scores)}`);
  if (result.issues.length > 0) {
    console.log(`    issues:`);
    result.issues.forEach((i) => console.log(`      - ${i}`));
  } else {
    console.log(`    issues:    (none)`);
  }
}

main().catch((err) => { console.error("Fatal:", err); process.exit(1); });
