import Database from "better-sqlite3";
import { readFileSync, readdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const MIGRATIONS_DIR = join(__dirname, "migrations");
const DATA_DIR = join(__dirname, "../../data");
const DB_PATH = join(DATA_DIR, "trendly.db");

let _db: Database.Database | null = null;

/**
 * Returns the singleton SQLite database instance.
 * Opens and migrates the DB on first call.
 */
export function getDb(): Database.Database {
  if (_db) return _db;
  _db = new Database(DB_PATH);
  _db.pragma("journal_mode = WAL");
  _db.pragma("foreign_keys = ON");
  runMigrations(_db);
  return _db;
}

/**
 * Closes the database connection. Mainly useful in tests.
 */
export function closeDb(): void {
  if (_db) {
    _db.close();
    _db = null;
  }
}

/**
 * Applies all pending SQL migrations in order.
 * Tracks applied migrations in the schema_version table.
 * Safe to call multiple times (idempotent).
 */
export function runMigrations(db: Database.Database): void {
  // Bootstrap the schema_version table if it doesn't exist yet
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_version (
      version     INTEGER PRIMARY KEY,
      applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);

  // Find the highest applied version
  const row = db.prepare("SELECT MAX(version) AS max_v FROM schema_version").get() as
    | { max_v: number | null }
    | undefined;
  const currentVersion = row?.max_v ?? 0;

  // Read .sql files in sorted order
  let files: string[];
  try {
    files = readdirSync(MIGRATIONS_DIR)
      .filter((f) => f.endsWith(".sql"))
      .sort();
  } catch {
    console.warn("[sqlite] No migrations directory found - skipping migrations");
    return;
  }

  for (const file of files) {
    // Extract version number from filename prefix (e.g. "001_init.sql" -> 1)
    const match = file.match(/^(\d+)/);
    if (!match) continue;
    const version = parseInt(match[1], 10);
    if (version <= currentVersion) continue;

    const sql = readFileSync(join(MIGRATIONS_DIR, file), "utf-8");
    console.log(`[sqlite] Applying migration ${file}`);
    db.exec(sql);
    // schema_version is inserted by the migration SQL itself (INSERT OR IGNORE)
    // But just to be safe, ensure the version row exists:
    db.prepare("INSERT OR IGNORE INTO schema_version(version) VALUES (?)").run(version);
  }
}
