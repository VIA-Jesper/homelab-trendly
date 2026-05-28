import { getDb } from "../store/sqlite.js";

// ─── content-registry v2: backed by SQLite published_products table ───────────
// Public API is unchanged from v1 so callers don't need updating.

/** Returns true if the product ID has already been published on the given site */
export function isProductUsed(siteKey: string, productId: string): boolean {
  const db = getDb();
  const row = db.prepare(
    "SELECT 1 FROM published_products WHERE site_key = ? AND product_id = ?"
  ).get(siteKey, productId);
  return row !== undefined;
}

/** Returns all used product IDs for a site */
export function getUsedProductIds(siteKey: string): string[] {
  const db = getDb();
  const rows = db.prepare(
    "SELECT product_id FROM published_products WHERE site_key = ?"
  ).all(siteKey) as Array<{ product_id: string }>;
  return rows.map((r) => r.product_id);
}

/**
 * Registers product IDs as published for a site.
 * Only call this when an article is actually published (not drafted).
 * run_id is optional - 0 used as sentinel when called from legacy code without a run.
 */
export function registerProducts(siteKey: string, productIds: string[], runId = 0): void {
  const db = getDb();
  const insert = db.prepare(
    "INSERT OR IGNORE INTO published_products (site_key, product_id, run_id) VALUES (?, ?, ?)"
  );
  const insertMany = db.transaction((ids: string[]) => {
    let count = 0;
    for (const id of ids) {
      const result = insert.run(siteKey, id, runId);
      count += result.changes;
    }
    return count;
  });
  const added = insertMany(productIds);
  if (added > 0) {
    console.log(`[content-registry] Registered ${added} products for site "${siteKey}"`);
  }
}

/** No-op in v2 (SQLite has no in-memory cache to invalidate). Kept for test compatibility. */
export function resetCache(): void {
  // no-op: SQLite doesn't use a file cache
}
