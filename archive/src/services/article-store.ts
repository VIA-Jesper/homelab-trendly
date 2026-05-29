import { getDb } from "../store/sqlite.js";
import type { ContentBrief } from "../types/index.js";
import type { ValidatorOutput, ReviewResult } from "../types/pipeline.js";

// ─── Types ────────────────────────────────────────────────────────────────────

export type RunStatus =
  | "created"
  | "briefed"
  | "generated"
  | "validating"
  | "reviewing"
  | "publishing"
  | "published"
  | "failed"
  | "needs_review";

export interface Run {
  id: number;
  site_key: string;
  trigger: string;
  category_id: string | null;
  status: RunStatus;
  brief_json: string | null;
  article_md: string | null;
  validation_json: string | null;
  review_json: string | null;
  wp_post_id: number | null;
  wp_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunPatch {
  status?: RunStatus;
  category_id?: string;
  brief_json?: string;
  article_md?: string;
  validation_json?: string;
  review_json?: string;
  wp_post_id?: number;
  wp_url?: string;
  error?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function createRun(siteKey: string, trigger: string): number {
  const db = getDb();
  const result = db.prepare(
    "INSERT INTO runs (site_key, trigger) VALUES (?, ?)"
  ).run(siteKey, trigger);
  return result.lastInsertRowid as number;
}

export function updateRun(id: number, patch: RunPatch): void {
  const db = getDb();
  const setClauses: string[] = ["updated_at = datetime('now')"];
  const values: unknown[] = [];

  for (const [key, value] of Object.entries(patch)) {
    if (value !== undefined) {
      setClauses.push(`${key} = ?`);
      values.push(value);
    }
  }

  values.push(id);
  db.prepare(`UPDATE runs SET ${setClauses.join(", ")} WHERE id = ?`).run(...values);
}

export function getRun(id: number): Run | undefined {
  const db = getDb();
  return db.prepare("SELECT * FROM runs WHERE id = ?").get(id) as Run | undefined;
}

export function listRuns(filter?: { siteKey?: string; status?: RunStatus; limit?: number }): Run[] {
  const db = getDb();
  let sql = "SELECT * FROM runs";
  const conditions: string[] = [];
  const values: unknown[] = [];

  if (filter?.siteKey) {
    conditions.push("site_key = ?");
    values.push(filter.siteKey);
  }
  if (filter?.status) {
    conditions.push("status = ?");
    values.push(filter.status);
  }
  if (conditions.length > 0) {
    sql += " WHERE " + conditions.join(" AND ");
  }
  sql += " ORDER BY created_at DESC";
  if (filter?.limit) {
    sql += " LIMIT ?";
    values.push(filter.limit);
  }

  return db.prepare(sql).all(...values) as Run[];
}

export function getRunsByStatus(status: RunStatus, siteKey?: string): Run[] {
  return listRuns({ status, siteKey });
}

// ─── Convenience: set brief on run ───────────────────────────────────────────

export function setBrief(runId: number, brief: ContentBrief): void {
  updateRun(runId, {
    status: "briefed",
    category_id: brief.category,
    brief_json: JSON.stringify(brief),
  });
}

export function setValidation(runId: number, validation: ValidatorOutput): void {
  updateRun(runId, {
    status: validation.passed ? "generated" : "needs_review",
    validation_json: JSON.stringify(validation),
  });
}

export function setReview(runId: number, review: ReviewResult): void {
  updateRun(runId, {
    status: "reviewing",
    review_json: JSON.stringify(review),
  });
}
