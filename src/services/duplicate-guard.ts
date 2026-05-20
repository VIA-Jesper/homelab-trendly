import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DATA_DIR = join(__dirname, "../../data");
const LOG_PATH = join(DATA_DIR, "published-log.json");
const LOG_TMP_PATH = join(DATA_DIR, "published-log.tmp.json");
import { renameSync } from "fs";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PublishedEntry {
  siteKey: string;
  category: string;       // e.g. "robotstovsugere"
  slug: string;           // e.g. "de-bedste-robotstovsugere-i-2025"
  focusKeyword: string;
  productIds: string[];
  publishedAt: string;    // ISO 8601
}

interface PublishedLog {
  articles: PublishedEntry[];
}

// ─── IO ───────────────────────────────────────────────────────────────────────

function loadLog(): PublishedLog {
  if (!existsSync(LOG_PATH)) return { articles: [] };
  try {
    return JSON.parse(readFileSync(LOG_PATH, "utf-8")) as PublishedLog;
  } catch {
    console.warn("[duplicate-guard] Failed to parse published-log.json — treating as empty");
    return { articles: [] };
  }
}

function saveLog(log: PublishedLog): void {
  mkdirSync(DATA_DIR, { recursive: true });
  writeFileSync(LOG_TMP_PATH, JSON.stringify(log, null, 2), "utf-8");
  renameSync(LOG_TMP_PATH, LOG_PATH);
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Returns true if an article for this category was published within cooldownDays.
 * Prevents writing "best robotstovsugere" twice in the same month.
 */
export function wasPublishedRecently(
  siteKey: string,
  category: string,
  cooldownDays: number
): boolean {
  const log = loadLog();
  const cutoff = Date.now() - cooldownDays * 24 * 60 * 60 * 1000;
  return log.articles.some(
    (a) =>
      a.siteKey === siteKey &&
      a.category.toLowerCase() === category.toLowerCase() &&
      new Date(a.publishedAt).getTime() > cutoff
  );
}

/**
 * Returns true if the exact focus keyword (or a very similar slug) is already published.
 * Guards against near-duplicate articles on the same topic.
 */
export function isDuplicateKeyword(siteKey: string, focusKeyword: string): boolean {
  const log = loadLog();
  const normalise = (s: string) => s.toLowerCase().replace(/[^a-zæøå0-9]/g, "");
  const target = normalise(focusKeyword);
  return log.articles.some(
    (a) => a.siteKey === siteKey && normalise(a.focusKeyword) === target
  );
}

/**
 * Logs a published article. Call this after successful WP publish (not before).
 */
export function logPublished(
  siteKey: string,
  category: string,
  slug: string,
  focusKeyword: string,
  productIds: string[]
): void {
  const log = loadLog();
  const entry: PublishedEntry = {
    siteKey,
    category,
    slug,
    focusKeyword,
    productIds,
    publishedAt: new Date().toISOString(),
  };
  log.articles.push(entry);
  saveLog(log);
  console.log(`[duplicate-guard] Logged "${slug}" for site "${siteKey}"`);
}

/**
 * Returns all published articles for a site, optionally filtered to last N days.
 */
export function getRecentPublished(siteKey: string, days?: number): PublishedEntry[] {
  const log = loadLog();
  const entries = log.articles.filter((a) => a.siteKey === siteKey);
  if (!days) return entries;
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return entries.filter((a) => new Date(a.publishedAt).getTime() > cutoff);
}
