import { z } from "zod";

// ─── Request Schemas ─────────────────────────────────────────────────────────

export const GenerateRequestSchema = z.object({
  category: z.string().optional(),
  productUrl: z.string().url().optional(),
  site: z.string().optional().default("techblog"),
}).refine(
  (data) => data.category !== undefined || data.productUrl !== undefined,
  { message: "Either 'category' or 'productUrl' must be provided" }
);

export const PublishRequestSchema = z.object({
  article: z.string().min(1, "Article content is required"),
  site: z.string().min(1, "Site key is required"),
});

// ─── Product & Brief Schemas ─────────────────────────────────────────────────

export const ProductBriefSchema = z.object({
  id: z.string(),
  name: z.string(),
  category: z.string(),
  priceKr: z.number(),
  retailer: z.string(),
  affiliateUrl: z.string().url(),
  specs: z.record(z.string(), z.string()),
});

export const ImageRefSchema = z.object({
  productId: z.string(),
  url: z.string().url(),
  alt: z.string(),
  caption: z.string(),
});

export const WritingRulesSchema = z.object({
  tone: z.enum(["neutral", "analytical", "friendly"]),
  minWords: z.number().int().positive(),
  maxWords: z.number().int().positive(),
  includeProsCons: z.boolean(),
  includeVerdict: z.boolean(),
});

export const ComplianceRulesSchema = z.object({
  requireDisclosure: z.boolean().default(true),
  disclosurePhrases: z.array(z.string()),
  forbiddenSuperlatives: z.array(z.string()),
});

export const ContentBriefSchema = z.object({
  brief_id: z.string().uuid(),
  category: z.string(),
  products: z.array(ProductBriefSchema).max(5),
  images: z.array(ImageRefSchema),
  writing_rules: WritingRulesSchema,
  compliance: ComplianceRulesSchema,
});

export const ValidationResultSchema = z.object({
  confidence_score: z.number().min(0).max(1),
  issues: z.array(z.string()),
  publish_mode: z.enum(["publish", "draft"]),
  article_with_placeholders: z.string(),
});

// Phase 1: file output. Phase 2: add wp_post_id / post_url here.
export const PublishResultSchema = z.object({
  status: z.enum(["saved"]),
  filePath: z.string(),
});

export const JobStatusSchema = z.enum(["pending", "briefed", "published", "failed"]);

export interface Job {
  job_id: string;
  status: z.infer<typeof JobStatusSchema>;
  brief?: z.infer<typeof ContentBriefSchema>;
  publishResult?: z.infer<typeof PublishResultSchema>;
  createdAt: Date;
  updatedAt: Date;
}

export interface SiteConfig {
  baseUrl: string;
  username: string;
  appPassword: string;
  defaultStatus: "publish" | "draft";
  categoryId: number;
  writingRules: z.infer<typeof WritingRulesSchema>;
}

export type GenerateRequest = z.infer<typeof GenerateRequestSchema>;
export type PublishRequest = z.infer<typeof PublishRequestSchema>;
export type ContentBrief = z.infer<typeof ContentBriefSchema>;
export type ProductBrief = z.infer<typeof ProductBriefSchema>;
export type ImageRef = z.infer<typeof ImageRefSchema>;
export type ValidationResult = z.infer<typeof ValidationResultSchema>;
export type PublishResult = z.infer<typeof PublishResultSchema>;
export type JobStatus = z.infer<typeof JobStatusSchema>;
export type WritingRules = z.infer<typeof WritingRulesSchema>;
export type ComplianceRules = z.infer<typeof ComplianceRulesSchema>;
