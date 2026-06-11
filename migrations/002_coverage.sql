-- Coverage ledger - the de-dup spine for the slot-based planner.
-- Mirrors api/models/coverage.py. Local SQLite is built from the models via
-- Base.metadata.create_all (scripts/load_prompts.py); this file keeps the
-- Postgres/docker path in sync.

-- One row per (job, product): "which products are covered on this site?"
CREATE TABLE job_products (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    site_id       UUID NOT NULL,
    product_key   VARCHAR(255) NOT NULL,
    name          VARCHAR(512) NOT NULL DEFAULT '',
    article_type  VARCHAR(50)  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- One row per job: its slot identity. Two live jobs must not share a slot_key
-- on the same site. primary_keyword/slug fill in progressively (slug at publish).
CREATE TABLE job_coverage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    site_id         UUID NOT NULL,
    slot_key        VARCHAR(512) NOT NULL,
    category_slug   VARCHAR(255) NOT NULL DEFAULT '',
    article_type    VARCHAR(50)  NOT NULL,
    primary_keyword VARCHAR(512),
    slug            VARCHAR(512),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_job_products_site_key   ON job_products(site_id, product_key);
CREATE INDEX idx_job_products_job        ON job_products(job_id);
CREATE INDEX idx_job_coverage_site_slot  ON job_coverage(site_id, slot_key);
CREATE INDEX idx_job_coverage_job        ON job_coverage(job_id);
