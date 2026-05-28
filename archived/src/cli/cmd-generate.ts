import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { generateBriefAsync } from "../services/brief-generator.js";
import { createRun, setBrief } from "../services/article-store.js";
import { SITE_CONFIGS } from "../config/sites.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadWritingInstructions(articleType: string): string {
  const paths = [
    join(__dirname, `../../prompts/agents/generator-types/${articleType}.md`),
    join(__dirname, "../../prompts/agents/generator.md"),
  ];
  for (const p of paths) {
    if (existsSync(p)) return readFileSync(p, "utf-8");
  }
  return "";
}

interface GenerateOpts {
  site: string;
  category?: string;
  productUrl?: string;
  json?: boolean;
}

export async function cmdGenerate(opts: GenerateOpts): Promise<void> {
  if (!SITE_CONFIGS[opts.site]) {
    console.error(`Unknown site: "${opts.site}". Available: ${Object.keys(SITE_CONFIGS).join(", ")}`);
    process.exit(1);
  }

  if (!opts.json) {
    console.log(`Generating brief for site: ${opts.site}...`);
    if (opts.category) console.log(`  Forcing category: ${opts.category}`);
    if (opts.productUrl) console.log(`  Forcing product URL: ${opts.productUrl}`);
    console.log("");
  }

  const result = await generateBriefAsync(
    opts.category,
    opts.productUrl,
    opts.site
  );

  if ("error" in result) {
    if (opts.json) {
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    } else {
      console.error(`Brief generation failed: ${result.error}`);
      if ("category" in result) console.error(`  Category: ${result.category}`);
    }
    process.exit(1);
  }

  const runId = createRun(opts.site, "cli");
  setBrief(runId, result);

  const writingInstructions = loadWritingInstructions(result.articleType ?? "standard");

  if (opts.json) {
    process.stdout.write(JSON.stringify({ run_id: runId, brief: result, writingInstructions }, null, 2) + "\n");
    return;
  }

  // Human-readable output
  console.log("=".repeat(60));
  console.log(`Run ID:   ${runId}`);
  console.log(`Category: ${result.category}`);
  console.log(`Type:     ${result.articleType}`);
  console.log(`Products: ${result.products.length}`);
  console.log("");
  console.log("Products to cover:");
  for (const p of result.products) {
    console.log(`  - ${p.name} (${p.priceKr} kr) — ${p.affiliateUrl}`);
  }
  console.log("");
  if (result.articleHook) console.log(`Hook:           ${result.articleHook}`);
  console.log(`Article type:   ${result.articleType ?? "standard"}`);
  console.log(`Word target:    ${result.writing_rules.minWords}-${result.writing_rules.maxWords} words`);
  console.log("=".repeat(60));
  console.log("");
  console.log("Next step:");
  console.log(`  Write the article, then validate:`);
  console.log(`  trendly validate --run ${runId} --article <your-article.md>`);
  console.log("");

  if (writingInstructions) {
    console.log("--- Writing Instructions ---");
    console.log(writingInstructions.slice(0, 800) + (writingInstructions.length > 800 ? "\n[...truncated - see prompts/agents/]" : ""));
  }
}
