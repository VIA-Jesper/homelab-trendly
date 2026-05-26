import { z } from "zod";
import type { ContentBrief, SeoPayload } from "./index.js";

// ─── Anchored Placement (replaces after_paragraph) ───────────────────────────

export const PlacementAnchorSchema = z.object({
  kind: z.enum(["after-heading", "before-heading", "end-of-section", "after-intro"]),
  section: z.string().describe("The heading text to anchor to (exact or prefix)"),
});

export const AnchoredPlacementSchema = z.object({
  type: z.enum(["image", "widget"]),
  productId: z.string(),
  anchor: PlacementAnchorSchema,
  after_paragraph: z.number().int().nonnegative().optional()
    .describe("DEPRECATED - only for migration compatibility"),
});

// ─── Step 2 output -> Step 3 input ───────────────────────────────────────────

export const PipelineBriefSchema = z.object({
  run_id: z.number().int(),
  site_key: z.string(),
  brief: z.any(), // ContentBrief - typed at runtime
  writing_instructions: z.string(),
});

// ─── Step 3 output -> Step 4 input ───────────────────────────────────────────

export const GeneratorOutputSchema = z.object({
  run_id: z.number().int(),
  article_md: z.string().min(1),
  placements: z.array(AnchoredPlacementSchema),
  seo: z.object({
    title: z.string().optional(),
    description: z.string().optional(),
    slug: z.string().optional(),
    focus_keyword: z.string().optional(),
    featured_image_product_id: z.string().optional(),
  }).optional(),
  article_type: z.string(),
});

// ─── Step 4 output ───────────────────────────────────────────────────────────

export const ValidatorErrorSchema = z.object({
  code: z.string()
    .describe("e.g. disclosure_missing | anchor_unresolved | word_count_low | superlative_found"),
  message: z.string(),
  severity: z.enum(["error", "warning"]),
});

export const ValidatorOutputSchema = z.object({
  passed: z.boolean(),
  errors: z.array(ValidatorErrorSchema),
  word_count: z.number().int(),
});

// ─── Step 5 output (per reviewer) ────────────────────────────────────────────

export const ReviewIssueSchema = z.object({
  severity: z.enum(["high", "medium", "low"]),
  area: z.string(),
  finding: z.string(),
  suggested_fix: z.string(),
});

export const ReviewerOutputSchema = z.object({
  reviewer: z.enum(["seo", "cro", "voice"]),
  score: z.number().int().min(0).max(100),
  verdict: z.enum(["pass", "fix", "rewrite"]),
  issues: z.array(ReviewIssueSchema),
  wins: z.array(z.string()),
});

// ─── Step 5 combined output ───────────────────────────────────────────────────

export const ReviewResultSchema = z.object({
  overall_score: z.number().int().min(0).max(100),
  reviewers: z.array(ReviewerOutputSchema),
  validator: ValidatorOutputSchema,
  needs_revision: z.boolean(),
  iteration: z.number().int().min(0),
});

// ─── Step 8 output ────────────────────────────────────────────────────────────

export const PublishOutputSchema = z.object({
  status: z.enum(["published", "draft", "rejected"]),
  wp_post_id: z.number().int().optional(),
  wp_url: z.string().url().optional(),
  gate_errors: z.array(ValidatorErrorSchema).optional(),
});

// ─── TypeScript types ─────────────────────────────────────────────────────────

export type PlacementAnchor = z.infer<typeof PlacementAnchorSchema>;
export type AnchoredPlacement = z.infer<typeof AnchoredPlacementSchema>;
export type PipelineBrief = z.infer<typeof PipelineBriefSchema>;
export type GeneratorOutput = z.infer<typeof GeneratorOutputSchema>;
export type ValidatorError = z.infer<typeof ValidatorErrorSchema>;
export type ValidatorOutput = z.infer<typeof ValidatorOutputSchema>;
export type ReviewIssue = z.infer<typeof ReviewIssueSchema>;
export type ReviewerOutput = z.infer<typeof ReviewerOutputSchema>;
export type ReviewResult = z.infer<typeof ReviewResultSchema>;
export type PublishOutput = z.infer<typeof PublishOutputSchema>;

// CritiquerOutput has same shape as GeneratorOutput
export type CritiquerOutput = GeneratorOutput;
