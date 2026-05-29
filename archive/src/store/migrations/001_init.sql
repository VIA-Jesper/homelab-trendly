-- Migration 001: Initial schema for Trendly v2
-- Tracks runs, published products, and article metrics.

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Each unique site (techblog, husforbegyndere, etc.)
CREATE TABLE IF NOT EXISTS sites (
  key         TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per pipeline run
CREATE TABLE IF NOT EXISTS runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_key        TEXT    NOT NULL REFERENCES sites(key),
  trigger         TEXT    NOT NULL DEFAULT 'manual',   -- 'manual' | 'cli' | 'mcp' | 'cron'
  category_id     TEXT,                               -- PR category slug/id
  status          TEXT    NOT NULL DEFAULT 'created',  -- created | briefed | generated | validating | reviewing | publishing | published | failed | needs_review
  brief_json      TEXT,   -- JSON blob of ContentBrief
  article_md      TEXT,   -- raw Markdown from generator
  validation_json TEXT,   -- JSON blob of ValidatorOutput
  review_json     TEXT,   -- JSON blob of ReviewResult
  wp_post_id      INTEGER,
  wp_url          TEXT,
  error           TEXT,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_site_status ON runs(site_key, status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);

-- Products that have been published (used to filter out already-written products)
CREATE TABLE IF NOT EXISTS published_products (
  site_key      TEXT    NOT NULL,
  product_id    TEXT    NOT NULL,
  run_id        INTEGER NOT NULL REFERENCES runs(id),
  published_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (site_key, product_id)
);

-- Reserved for v2: performance tracking (GA4, clicks, etc.)
CREATE TABLE IF NOT EXISTS article_metrics (
  run_id          INTEGER PRIMARY KEY REFERENCES runs(id),
  ga4_pageviews   INTEGER,
  ga4_sessions    INTEGER,
  click_through   REAL,
  measured_at     TEXT
);

-- Seed built-in sites
INSERT OR IGNORE INTO sites(key, name) VALUES ('techblog', 'Techblog DK');
INSERT OR IGNORE INTO sites(key, name) VALUES ('husforbegyndere', 'Hus for Begyndere');

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
