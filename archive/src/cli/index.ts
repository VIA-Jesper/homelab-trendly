#!/usr/bin/env node
/**
 * Trendly CLI
 *
 * Usage:
 *   trendly setup                              Check env + run migrations
 *   trendly generate --site <site>             Find gap, generate brief, create run
 *   trendly generate --site <site> --category laptops
 *   trendly validate --run <id> --article <file>
 *   trendly publish  --run <id> --article <file> [--live]
 *   trendly runs [--site <site>] [--limit 20]
 *   trendly runs show <id>
 */

import "dotenv/config";
import { Command } from "commander";
import { cmdSetup } from "./cmd-setup.js";
import { cmdGenerate } from "./cmd-generate.js";
import { cmdValidate } from "./cmd-validate.js";
import { cmdPublish } from "./cmd-publish.js";
import { cmdRuns } from "./cmd-runs.js";

const program = new Command();

program
  .name("trendly")
  .description("Agentic affiliate article pipeline")
  .version("2.0.0");

// ─── setup ────────────────────────────────────────────────────────────────────
program
  .command("setup")
  .description("Validate environment, run DB migrations, test WP connectivity")
  .option("--site <site>", "Test a specific site (default: all configured sites)")
  .action(cmdSetup);

// ─── generate ─────────────────────────────────────────────────────────────────
program
  .command("generate")
  .description("Find category gap, generate brief, create a run. Outputs brief + writing instructions.")
  .requiredOption("--site <site>", "Site key, e.g. techblog or husforbegyndere")
  .option("--category <slug>", "Force a specific category slug instead of auto-discovery")
  .option("--product-url <url>", "Force a specific product URL")
  .option("--json", "Output raw JSON instead of formatted text")
  .action(cmdGenerate);

// ─── validate ─────────────────────────────────────────────────────────────────
program
  .command("validate")
  .description("Validate a Markdown article against its run brief")
  .requiredOption("--run <id>", "Run ID returned by generate", parseInt)
  .requiredOption("--article <file>", "Path to the Markdown article file")
  .option("--json", "Output raw JSON")
  .action(cmdValidate);

// ─── publish ──────────────────────────────────────────────────────────────────
program
  .command("publish")
  .description("Publish a validated article to WordPress (draft by default)")
  .requiredOption("--run <id>", "Run ID returned by generate", parseInt)
  .requiredOption("--article <file>", "Path to the Markdown article file")
  .option("--live", "Publish live instead of saving as draft")
  .option("--json", "Output raw JSON")
  .action(cmdPublish);

// ─── runs ──────────────────────────────────────────────────────────────────────
program
  .command("runs [show] [id]")
  .description("List recent runs, or show details of a specific run")
  .option("--site <site>", "Filter by site key")
  .option("--status <status>", "Filter by status")
  .option("--limit <n>", "Max results (default: 20)", parseInt)
  .option("--json", "Output raw JSON")
  .action(cmdRuns);

program.parseAsync(process.argv);
