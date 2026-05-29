/**
 * One-shot migration script: imports v1 JSON data into SQLite.
 * Run once after first trendly setup.
 *
 * Usage: npx tsx src/store/migrate-json-to-sqlite.ts
 */

import { readFileSync, existsSync, renameSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { getDb, closeDb } from "./sqlite.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DATA_DIR = join(__dirname, "../../data");

interface V1Registry {
  [siteKey: string]: string[];
}

interface V1PublishedEntry {
  siteKey: string;
  category: string;
  slug: string;
  focusKeyword: string;
  productIds: string[];
  publishedAt: string;
}

interface V1PublishedLog {
  articles: V1PublishedEntry[];
}

function migrateContentRegistry(db: ReturnType<typeof getDb>): void {
  const path = join(DATA_DIR, "content-registry.json");
  if (!existsSync(path)) {
    console.log("[migrate] content-registry.json not found — skipping");
    return;
  }

  const registry = JSON.parse(readFileSync(path, "utf-8")) as V1Registry;
  const insert = db.prepare(
    "INSERT OR IGNORE INTO published_products (site_key, product_id, run_id) VALUES (?, ?, 0)"
  );
  const insertMany = db.transaction(() => {
    let count = 0;
    for (const [siteKey, productIds] of Object.entries(registry)) {
      for (const productId of productIds) {
        const result = insert.run(siteKey, productId);
        count += result.changes;
      }
    }
    return count;
  });

  const added = insertMany();
  console.log(`[migrate] content-registry: imported ${added} product registrations`);
  renameSync(path, path + ".legacy");
  console.log(`[migrate] Renamed content-registry.json to content-registry.json.legacy`);
}

function migratePublishedLog(db: ReturnType<typeof getDb>): void {
  const path = join(DATA_DIR, "published-log.json");
  if (!existsSync(path)) {
    console.log("[migrate] published-log.json not found — skipping");
    return;
  }

  const log = JSON.parse(readFileSync(path, "utf-8")) as V1PublishedLog;
  if (!log.articles?.length) {
    console.log("[migrate] published-log.json is empty — skipping");
    return;
  }

  const insertRun = db.prepare(`
    INSERT OR IGNORE INTO runs (site_key, trigger, category_id, status, wp_url, created_at, updated_at)
    VALUES (?, 'migrated', ?, 'published', ?, ?, ?)
  `);
  const insertProduct = db.prepare(
    "INSERT OR IGNORE INTO published_products (site_key, product_id, run_id, published_at) VALUES (?, ?, ?, ?)"
  );

  const migrate = db.transaction(() => {
    let runCount = 0;
    for (const entry of log.articles) {
      const result = insertRun.run(
        entry.siteKey,
        entry.category,
        entry.slug,
        entry.publishedAt,
        entry.publishedAt
      );
      const runId = result.lastInsertRowid as number;
      if (result.changes > 0) {
        runCount++;
        for (const productId of entry.productIds) {
          insertProduct.run(entry.siteKey, productId, runId, entry.publishedAt);
        }
      }
    }
    return runCount;
  });

  const runs = migrate();
  console.log(`[migrate] published-log: imported ${runs} published run(s)`);
  renameSync(path, path + ".legacy");
  console.log(`[migrate] Renamed published-log.json to published-log.json.legacy`);
}

async function main(): Promise<void> {
  console.log("[migrate] Starting JSON -> SQLite migration...");
  const db = getDb();
  migrateContentRegistry(db);
  migratePublishedLog(db);
  console.log("[migrate] Migration complete.");
  closeDb();
}

main().catch((err) => {
  console.error("[migrate] Error:", err);
  process.exit(1);
});
