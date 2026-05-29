import { listRuns, getRun } from "../services/article-store.js";
import type { Run, RunStatus } from "../services/article-store.js";

interface RunsOpts {
  site?: string;
  status?: string;
  limit?: number;
  json?: boolean;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" });
}

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    published: "PUBLISHED",
    failed: "FAILED   ",
    needs_review: "NEEDS FIX",
    briefed: "BRIEFED  ",
    publishing: "PUBLISH..",
    generated: "GENERATED",
    created: "CREATED  ",
  };
  return map[status] ?? status.padEnd(9).toUpperCase();
}

export async function cmdRuns(subcommand: string | undefined, id: string | undefined, opts: RunsOpts): Promise<void> {
  // runs show <id>
  if (subcommand === "show" && id) {
    const run = getRun(parseInt(id));
    if (!run) {
      console.error(`Run ${id} not found.`);
      process.exit(1);
    }

    if (opts.json) {
      process.stdout.write(JSON.stringify(run, null, 2) + "\n");
      return;
    }

    console.log(`\nRun #${run.id} — ${run.site_key} [${run.status}]`);
    console.log(`Trigger:   ${run.trigger}`);
    console.log(`Category:  ${run.category_id ?? "-"}`);
    console.log(`Created:   ${formatDate(run.created_at)}`);
    console.log(`Updated:   ${formatDate(run.updated_at)}`);
    if (run.wp_url)     console.log(`WP URL:    ${run.wp_url}`);
    if (run.wp_post_id) console.log(`WP Post:   ${run.wp_post_id}`);
    if (run.error)      console.log(`Error:     ${run.error}`);

    if (run.validation_json) {
      const v = JSON.parse(run.validation_json);
      console.log(`\nValidation: ${v.passed ? "PASSED" : "FAILED"} (${v.word_count} words)`);
      if (v.errors?.length > 0) {
        for (const e of v.errors) {
          console.log(`  [${e.severity?.toUpperCase()}] ${e.code}: ${e.message}`);
        }
      }
    }

    if (run.brief_json) {
      const b = JSON.parse(run.brief_json);
      console.log(`\nBrief: ${b.suggestedTitle ?? b.category}`);
      console.log(`Type:  ${b.articleType}`);
      console.log(`Focus: ${b.focusKeyword}`);
    }
    return;
  }

  // runs list (default)
  const runs = listRuns({
    siteKey: opts.site,
    status: opts.status as RunStatus | undefined,
    limit: opts.limit ?? 20,
  });

  if (opts.json) {
    process.stdout.write(JSON.stringify(runs, null, 2) + "\n");
    return;
  }

  if (runs.length === 0) {
    console.log("No runs found.");
    return;
  }

  console.log("");
  console.log(" ID   STATUS      SITE              CATEGORY             CREATED");
  console.log(" " + "-".repeat(75));
  for (const run of runs) {
    const id = String(run.id).padStart(4);
    const status = statusBadge(run.status);
    const site = run.site_key.padEnd(16).slice(0, 16);
    const cat = (run.category_id ?? "-").padEnd(20).slice(0, 20);
    const date = formatDate(run.created_at);
    console.log(` ${id}  ${status}  ${site}  ${cat}  ${date}`);
  }
  console.log("");
}
