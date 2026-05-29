-- Affiliate Pipeline - Initial Schema
-- JSONB fields allow adding products/SEO/links/widgets later without schema changes

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Sites: one row per affiliate site
CREATE TABLE sites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    domain      VARCHAR(255) NOT NULL UNIQUE,
    seed        JSONB NOT NULL DEFAULT '{}',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prompts: versioned prompt store - update content here without redeploy
CREATE TABLE prompts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    version     VARCHAR(20)  NOT NULL,
    content     TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);

-- Jobs: one row per article to generate
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES sites(id),
    status      VARCHAR(50) NOT NULL DEFAULT 'queued',
    context     JSONB NOT NULL DEFAULT '{}',
    reasoning   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Steps: individual pipeline steps within a job
CREATE TABLE steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_name       VARCHAR(100) NOT NULL,
    step_order      INTEGER NOT NULL,
    prompt_id       UUID REFERENCES prompts(id),
    input           JSONB,
    output          TEXT,
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    attempt         INTEGER NOT NULL DEFAULT 1,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    UNIQUE (job_id, step_name, attempt)
);

CREATE INDEX idx_jobs_status  ON jobs(status);
CREATE INDEX idx_jobs_site_id ON jobs(site_id);
CREATE INDEX idx_steps_job_id ON steps(job_id);
CREATE INDEX idx_steps_status ON steps(status);
CREATE INDEX idx_prompts_name_active ON prompts(name, is_active);

-- Seed placeholder prompts (update content via API or SQL)
INSERT INTO prompts (name, version, content) VALUES
    ('generate_post', 'v1', 'PLACEHOLDER'),
    ('optimize_seo',  'v1', 'PLACEHOLDER'),
    ('qa_review',     'v1', 'PLACEHOLDER');
