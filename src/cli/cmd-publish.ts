import { readFileSync, existsSync } from "fs";
import { getRun } from "../services/article-store.js";
import { publish } from "../services/publish-service.js";
import type { ContentBrief } from "../types/index.js";

interface PublishOpts {
  run: number;
  article: string;
  live?: boolean;
  json?: boolean;
}

export async function cmdPublish(opts: PublishOpts): Promise<void> {
  // Load run
  const run = getRun(opts.run);
  if (!run?.brief_json) {
    console.error(`Run ${opts.run} not found or has no brief.`);
    process.exit(1);
  }

  // Load article file
  if (!existsSync(opts.article)) {
    console.error(`Article file not found: ${opts.article}`);
    process.exit(1);
  }
  const article = readFileSync(opts.article, "utf-8");
  const brief = JSON.parse(run.brief_json) as ContentBrief;
  const status = opts.live ? "publish" : "draft";

  if (!opts.json) {
    console.log(`Publishing run ${opts.run} to ${run.site_key} as "${status}"...`);
    console.log("");
  }

  const result = await publish({
    runId: opts.run,
    article,
    brief,
    siteKey: run.site_key,
    placements: [],
    status,
  });

  if (opts.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    process.exit(result.status === "rejected" ? 1 : 0);
  }

  // Human-readable output
  console.log("=".repeat(60));

  if (result.status === "rejected") {
    console.log("REJECTED - hard gate failed:");
    for (const e of result.gate_errors ?? []) {
      console.log(`  [GATE] ${e.code}: ${e.message}`);
    }
    console.log("");
    console.log("Fix the errors above, then re-validate:");
    console.log(`  trendly validate --run ${opts.run} --article ${opts.article}`);
    process.exit(1);
  }

  console.log(`Status:   ${result.status.toUpperCase()}`);
  if (result.wp_post_id) console.log(`WP Post:  ${result.wp_post_id}`);
  if (result.wp_url)    console.log(`URL:      ${result.wp_url}`);
  console.log("=".repeat(60));

  if (result.status === "draft") {
    console.log("");
    console.log("Saved as draft. When ready to go live:");
    console.log(`  trendly publish --run ${opts.run} --article ${opts.article} --live`);
  }
}
