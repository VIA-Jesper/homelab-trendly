import { getDb } from "../store/sqlite.js";

// ─── duplicate-guard v2: backed by SQLite runs table ─────────────────────────
// Public API unchanged from v1.

export interface PublishedEntry {
  siteKey: string;
  category: string;
  slug: string;
  focusKeyword: string;
  productIds: string[];
  publishedAt: string;
}

/**
 * Returns true if an article for this category was published within cooldownDays.
 */
export function wasPublishedRecently(
  siteKey: string,
  category: string,
  cooldownDays: number
): boolean {
  const db = getDb();
  const row = db.prepare(`
    SELECT 1 FROM runs
    WHERE site_key = ?
      AND lower(category_id) = lower(?)
      AND status = 'published'
      AND created_at > datetime('now', ?)
    LIMIT 1
  `).get(siteKey, category, `-${cooldownDays} days`);
  return row !== undefined;
}

/**
 * Returns true if the exact focus keyword is already published on this site.
 */
export function isDuplicateKeyword(siteKey: string, focusKeyword: string): boolean {
  const db = getDb();
  // wp_url contains the slug; check runs where wp_url includes the normalised keyword
  const normalise = (s: string) => s.toLowerCase().replace(/[^a-zæøå0-9]/g, "");
  const target = normalise(focusKeyword);
  const runs = db.prepare(
    "SELECT wp_url FROM runs WHERE site_key = ? AND status = 'published'"
  ).all(siteKey) as Array<{ wp_url: string | null }>;
  return runs.some((r) => r.wp_url && normalise(r.wp_url).includes(target));
}

/**
 * Logs a published article. In v2 the run record already exists in SQLite;
 * this updates it with wp_url and marks it published.
 * For backward compat when called from legacy code, a no-op sentinel run is created.
 */
export function logPublished(
  siteKey: string,
  category: string,
  slug: string,
  focusKeyword: string,
  productIds: string[]
): void {
  // This is only called from legacy MCP path now.
  // The publish-service takes care of updating run status in v2.
  // We keep this as a no-op to avoid breaking callers during migration.
  console.log(`[duplicate-guard] logPublished called for "${slug}" on "${siteKey}" (v2: handled by publish-service)`);
  void { category, slug, focusKeyword, productIds }; // suppress unused-var
}

/**
 * Returns published runs for a site, optionally limited to last N days.
 */
export function getRecentPublished(siteKey: string, days?: number): PublishedEntry[] {
  const db = getDb();
  let sql = `SELECT category_id, wp_url, created_at FROM runs WHERE site_key = ? AND status = 'published'`;
  const params: unknown[] = [siteKey];
  if (days) {
    sql += ` AND created_at > datetime('now', ?)`;
    params.push(`-${days} days`);
  }
  const rows = db.prepare(sql).all(...params) as Array<{
    category_id: string | null;
    wp_url: string | null;
    created_at: string;
  }>;
  return rows.map((r) => ({
    siteKey,
    category: r.category_id ?? "",
    slug: r.wp_url ?? "",
    focusKeyword: "",
    productIds: [],
    publishedAt: r.created_at,
  }));
}
