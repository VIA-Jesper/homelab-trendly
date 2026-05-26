import type { SeoPayload } from "../types/index.js";
import type { AnchoredPlacement } from "../types/index.js";
import type { PublishOutput } from "../types/pipeline.js";
import { validateArticleV2 } from "./validator.js";
import { publishToWordPress } from "./wp-publisher.js";
import { registerProducts } from "./content-registry.js";
import { updateRun } from "./article-store.js";
import type { ContentBrief } from "../types/index.js";

// ─── Options ─────────────────────────────────────────────────────────────────

export interface PublishServiceOptions {
  runId: number;
  article: string;
  brief: ContentBrief;
  siteKey: string;
  placements: AnchoredPlacement[];
  seo?: SeoPayload;
  /** Defaults to "draft" for safety */
  status?: "publish" | "draft";
  /** When true, skip the hard gate checks (test/debug only) */
  skipGate?: boolean;
}

// ─── Publish service ──────────────────────────────────────────────────────────

/**
 * Single source of truth for publishing articles.
 *
 * - Runs hard gate validation (disclosure, superlatives, word count, anchors)
 * - If gate fails → returns rejected with gate_errors; does NOT call WP
 * - If gate passes → calls wp-publisher to POST to WordPress
 * - Updates run status in SQLite
 * - Registers products in published_products on publish (not draft)
 * - Defaults to "draft" status
 */
export async function publish(options: PublishServiceOptions): Promise<PublishOutput> {
  const {
    runId,
    article,
    brief,
    siteKey,
    placements,
    seo,
    status = "draft",
    skipGate = false,
  } = options;

  // ── Hard gate ─────────────────────────────────────────────────────────────
  if (!skipGate) {
    const validation = validateArticleV2(article, brief, placements, siteKey);
    const hardErrors = validation.errors.filter((e) => e.severity === "error");

    if (!validation.passed || hardErrors.length > 0) {
      updateRun(runId, {
        status: "needs_review",
        validation_json: JSON.stringify(validation),
        article_md: article,
      });
      return {
        status: "rejected",
        gate_errors: hardErrors,
      };
    }

    // Store validation result even on pass
    updateRun(runId, {
      validation_json: JSON.stringify(validation),
      article_md: article,
    });
  }

  // ── Publish to WordPress ──────────────────────────────────────────────────
  updateRun(runId, { status: "publishing" });

  let wpResult: Awaited<ReturnType<typeof publishToWordPress>>;
  try {
    wpResult = await publishToWordPress({
      jobId: String(runId),
      article,
      brief,
      siteKey,
      status,
      placements: [], // insertAnchoredPlacements called inside wp-publisher Phase 4.2
      seo,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    updateRun(runId, { status: "failed", error: msg });
    throw err;
  }

  // ── Update run + register products ───────────────────────────────────────
  const finalStatus = status === "publish" ? "published" : "briefed";
  updateRun(runId, {
    status: finalStatus as "published" | "briefed",
    wp_post_id: wpResult.wp_post_id,
    wp_url: wpResult.url,
  });

  if (status === "publish") {
    const productIds = brief.products.map((p) => p.id);
    registerProducts(siteKey, productIds, runId);
  }

  return {
    status: status === "publish" ? "published" : "draft",
    wp_post_id: wpResult.wp_post_id,
    wp_url: wpResult.url,
  };
}
