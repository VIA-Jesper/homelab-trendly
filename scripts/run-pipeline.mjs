/**
 * Run the full article pipeline using MCP tools directly.
 * This bypasses the MCP HTTP server and calls the tools inline.
 */
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

// Set up env for husforbegyndere
process.env["WP_HUS_URL"] = "https://husforbegyndere.dk";
process.env["WP_HUS_USER"] = "vnisq8";
process.env["WP_HUS_APP_PASSWORD"] = "In11 CAkL 9jrz dQ5e gdpf BDK1";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";

// Import the services directly
import { generateBriefAsync } from "../src/services/brief-generator.js";
import { publishToWordPress } from "../src/services/wp-publisher.js";
import { validateArticleFull } from "../src/services/validator.js";
import { insertPlacements } from "../src/services/widget-inserter.js";
import { convertMarkdownToHtml } from "../src/services/markdown-renderer.js";
import { appendPartnerIdToPrLinks } from "../src/services/affiliate-linker.js";

const CATEGORY = "robotstøvsugere";
const SITE = "husforbegyndere";

console.log(`\n=== PHASE 0: Initialize ===`);
console.log(`Category: ${CATEGORY}, Site: ${SITE}`);

// PHASE 1: Get brief via MCP get_brief equivalent
console.log(`\n=== PHASE 1: Generate Brief ===`);
const briefResult = await generateBriefAsync({
  category: CATEGORY,
  site: SITE
});

if (briefResult.error) {
  console.log(`Brief error: ${briefResult.error} - ${briefResult.category}`);
  // Try without category (auto-discover)
  console.log("Trying auto-discover...");
  const autoResult = await generateBriefAsync({ site: SITE });
  if (autoResult.error) {
    console.log(`Auto-discover also failed: ${autoResult.error}`);
    process.exit(1);
  }
  console.log(`Auto-discovered category: ${autoResult.brief?.category}`);
} else {
  console.log(`Brief generated: ${briefResult.brief?.category}`);
  console.log(`Products: ${briefResult.brief?.products?.length}`);
  console.log(`Article type: ${briefResult.brief?.articleType}`);
  console.log(`Hook: ${briefResult.brief?.articleHook}`);
}

console.log("\nDone!");
