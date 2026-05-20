import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DATA_DIR = join(__dirname, "../../data");
const REGISTRY_PATH = join(DATA_DIR, "content-registry.json");
const REGISTRY_TMP_PATH = join(DATA_DIR, "content-registry.tmp.json");

type Registry = Record<string, string[]>;

let _cache: Registry | null = null;

function loadRegistry(): Registry {
  if (_cache) return _cache;
  if (!existsSync(REGISTRY_PATH)) {
    _cache = {};
    return _cache;
  }
  try {
    const raw = readFileSync(REGISTRY_PATH, "utf-8");
    _cache = JSON.parse(raw) as Registry;
    return _cache;
  } catch {
    console.warn("[content-registry] Failed to parse registry — treating as empty");
    _cache = {};
    return _cache;
  }
}

function saveRegistry(registry: Registry): void {
  mkdirSync(DATA_DIR, { recursive: true });
  // Atomic write: write to temp file first, then rename
  writeFileSync(REGISTRY_TMP_PATH, JSON.stringify(registry, null, 2), "utf-8");
  renameSync(REGISTRY_TMP_PATH, REGISTRY_PATH);
}

/** Returns true if the product ID has already been published on the given site */
export function isProductUsed(siteKey: string, productId: string): boolean {
  const registry = loadRegistry();
  return (registry[siteKey] ?? []).includes(productId);
}

/** Returns all used product IDs for a site */
export function getUsedProductIds(siteKey: string): string[] {
  const registry = loadRegistry();
  return registry[siteKey] ?? [];
}

/**
 * Registers product IDs as published for a site.
 * Only call this when an article is actually published (not drafted).
 */
export function registerProducts(siteKey: string, productIds: string[]): void {
  const registry = loadRegistry();
  const existing = registry[siteKey] ?? [];
  const toAdd = productIds.filter((id) => !existing.includes(id));
  if (toAdd.length === 0) return;
  registry[siteKey] = [...existing, ...toAdd];
  _cache = registry;
  saveRegistry(registry);
  console.log(`[content-registry] Registered ${toAdd.length} products for site "${siteKey}"`);
}

/** Invalidates in-memory cache (useful in tests) */
export function resetCache(): void {
  _cache = null;
}
