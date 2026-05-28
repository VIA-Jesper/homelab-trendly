import { readFileSync, existsSync } from "fs";
import { getRun, setValidation } from "../services/article-store.js";
import { validateArticleV2 } from "../services/validator.js";
import type { ContentBrief } from "../types/index.js";

interface ValidateOpts {
  run: number;
  article: string;
  json?: boolean;
}

export async function cmdValidate(opts: ValidateOpts): Promise<void> {
  // Load run
  const run = getRun(opts.run);
  if (!run?.brief_json) {
    console.error(`Run ${opts.run} not found or has no brief. Run "trendly generate" first.`);
    process.exit(1);
  }

  // Load article file
  if (!existsSync(opts.article)) {
    console.error(`Article file not found: ${opts.article}`);
    process.exit(1);
  }
  const article = readFileSync(opts.article, "utf-8");
  const brief = JSON.parse(run.brief_json) as ContentBrief;

  // Validate
  const result = validateArticleV2(article, brief, [], run.site_key);
  setValidation(opts.run, result);

  if (opts.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    process.exit(result.passed ? 0 : 1);
  }

  // Human-readable output
  console.log("=".repeat(60));
  console.log(`Validation: ${result.passed ? "PASSED" : "FAILED"}`);
  console.log(`Word count: ${result.word_count}`);
  console.log(`Run ID:     ${opts.run}`);
  console.log("");

  if (result.errors.length === 0) {
    console.log("No issues found. Ready to publish.");
  } else {
    const errors = result.errors.filter((e) => e.severity === "error");
    const warnings = result.errors.filter((e) => e.severity === "warning");

    if (errors.length > 0) {
      console.log(`Errors (${errors.length}) - must fix before publishing:`);
      for (const e of errors) {
        console.log(`  [ERROR] ${e.code}: ${e.message}`);
      }
      console.log("");
    }

    if (warnings.length > 0) {
      console.log(`Warnings (${warnings.length}):`);
      for (const w of warnings) {
        console.log(`  [WARN]  ${w.code}: ${w.message}`);
      }
    }
  }

  console.log("=".repeat(60));

  if (result.passed) {
    console.log("");
    console.log("Next step:");
    console.log(`  trendly publish --run ${opts.run} --article ${opts.article}`);
    console.log(`  trendly publish --run ${opts.run} --article ${opts.article} --live`);
  }

  process.exit(result.passed ? 0 : 1);
}
