import axios from "axios";
import { SITE_CONFIGS } from "../config/sites.js";
import { getDb, closeDb } from "../store/sqlite.js";

export async function cmdSetup(opts: { site?: string }): Promise<void> {
  let ok = true;

  console.log("=== Trendly Setup ===\n");

  // 1. SQLite migrations
  try {
    getDb(); // triggers runMigrations()
    console.log("  [OK] SQLite migrations applied");
  } catch (err) {
    console.error("  [FAIL] SQLite:", err instanceof Error ? err.message : err);
    ok = false;
  }

  // 2. Check site env vars + WP connectivity
  const siteKeys = opts.site
    ? [opts.site]
    : Object.keys(SITE_CONFIGS);

  for (const key of siteKeys) {
    const cfg = SITE_CONFIGS[key];
    if (!cfg) {
      console.error(`  [FAIL] Unknown site key: ${key}`);
      ok = false;
      continue;
    }

    process.stdout.write(`\nSite: ${key} (${cfg.baseUrl})\n`);

    // Env var check
    const missing: string[] = [];
    if (!cfg.username) missing.push(`WP_${key.toUpperCase()}_USER`);
    if (!cfg.appPassword) missing.push(`WP_${key.toUpperCase()}_APP_PASSWORD`);
    if (cfg.baseUrl.includes("example.dk")) missing.push(`WP_${key.toUpperCase()}_BASE_URL`);

    if (missing.length > 0) {
      console.error(`  [FAIL] Missing env vars: ${missing.join(", ")}`);
      ok = false;
      continue;
    }
    console.log("  [OK]  Env vars present");

    // WP connectivity (GET /wp-json/wp/v2/posts?per_page=1)
    try {
      const url = `${cfg.baseUrl.replace(/\/$/, "")}/wp-json/wp/v2/posts?per_page=1`;
      const res = await axios.get(url, {
        auth: { username: cfg.username, password: cfg.appPassword },
        timeout: 8000,
      });
      console.log(`  [OK]  WP REST API reachable (status ${res.status})`);
    } catch (err) {
      const msg = axios.isAxiosError(err)
        ? `HTTP ${err.response?.status ?? "timeout"}: ${err.message}`
        : String(err);
      console.error(`  [FAIL] WP connectivity: ${msg}`);
      ok = false;
    }

    // PriceRunner partner ID
    if (!cfg.pricerunnerPartnerId) {
      console.warn(`  [WARN] PR_${key.toUpperCase()}_PARTNER_ID not set (scraping disabled)`);
    } else {
      console.log("  [OK]  PriceRunner partner ID present");
    }
  }

  console.log(`\n${ok ? "Setup OK - ready to generate." : "Setup has errors - fix above before generating."}`);
  closeDb();
  process.exit(ok ? 0 : 1);
}
