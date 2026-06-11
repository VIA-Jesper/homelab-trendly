import type { ContentBrief, ValidationResult, Placement, AnchoredPlacement } from "../types/index.js";
import type { ValidatorOutput, ValidatorError } from "../types/pipeline.js";
import { getTypeRules } from "./article-type-config.js";
import { insertAnchoredPlacements } from "./widget-inserter.js";

// ─── MCP-facing rich validation ───────────────────────────────────────────────

export interface McpValidationResult {
  passed: boolean;
  wordCount: number;
  issues: string[];
  scores: { seo: number; voice: number; cro: number };
}

export function validateArticleFull(
  article: string,
  brief: ContentBrief,
  placements: Placement[]
): McpValidationResult {
  const issues: string[] = [];
  const articleLower = article.toLowerCase();
  const typeRules = getTypeRules(brief.articleType);

  // Word count
  const wordCount = article.trim().split(/\s+/).filter(Boolean).length;
  if (wordCount < typeRules.minWords) {
    issues.push(`Word count ${wordCount} below minimum ${typeRules.minWords} for type "${typeRules.articleType}"`);
  } else if (wordCount > typeRules.maxWords) {
    issues.push(`Word count ${wordCount} exceeds maximum ${typeRules.maxWords} for type "${typeRules.articleType}"`);
  }

  // Disclosure in first 300 chars (optional - site-wide banner handles it)
  const opening = article.slice(0, 300).toLowerCase();
  const hasDisclosure = brief.compliance.disclosurePhrases.some((p) => opening.includes(p.toLowerCase()));
  if (!hasDisclosure && brief.compliance.requireDisclosure) {
    issues.push("Missing affiliate disclosure in opening 300 characters");
  }

  // Forbidden superlatives
  for (const term of brief.compliance.forbiddenSuperlatives) {
    if (articleLower.includes(term.toLowerCase())) {
      issues.push(`Forbidden term found: "${term}"`);
    }
  }

  // Verdict
  if (typeRules.requireVerdict && !/vores dom|konklusion|sammenfattende/i.test(article)) {
    issues.push("Missing 'Vores dom' verdict section");
  }

  // Pros/Cons
  if (typeRules.requireProsCons && !/fordele|ulemper|det vi kan lide|det vi ville \u00e6ndre/i.test(article)) {
    issues.push(`Missing pros/cons sections (required for type "${typeRules.articleType}")`);
  }

  // Product coverage
  for (const product of brief.products) {
    const shortName = product.name.slice(0, 30).toLowerCase();
    if (!articleLower.includes(shortName)) {
      issues.push(`Product may be missing from article: "${product.name.slice(0, 40)}"`);
    }
  }

  // Placement sanity
  const paragraphs = article.split(/\r?\n\s*\r?\n/);
  const paraCount = paragraphs.length;
  for (const p of placements) {
    if (p.after_paragraph >= paraCount) {
      issues.push(`Placement out of range: ${p.type} for ${p.productId} at paragraph ${p.after_paragraph} (max: ${paraCount - 1})`);
    }
  }

  // ── Scores ────────────────────────────────────────────────────────────────
  let seoScore = 100;
  const paragraphTexts = paragraphs.map((p) => p.toLowerCase());

  if (!article.includes("## ")) seoScore -= 20;
  // First body paragraph keyword check is skipped here since we don't have seo.focus_keyword in brief

  let voiceScore = 100;
  const foundTells = typeRules.aiTells.filter((t) => articleLower.includes(t.toLowerCase()));
  voiceScore -= Math.min(50, foundTells.length * 10);
  // Spelling consistency: robotstovsugere vs robotstøvsugere
  if (article.includes("robotstovsugere") && article.includes("robotst\u00f8vsugere")) voiceScore -= 15;

  let croScore = 100;
  const lastPara = paragraphTexts[paragraphTexts.length - 1] ?? "";
  const { verdictAffiliate, placementDensity } = typeRules.croWeights;
  if (!lastPara.includes("http")) croScore -= verdictAffiliate;

  const heroTypes = new Set(["hero"]);
  const expectedPlacements = heroTypes.has(typeRules.articleType)
    ? brief.products.length + 1
    : typeRules.articleType === "single-product-review"
      ? 2
      : brief.products.length * 2;
  if (placements.length < expectedPlacements) croScore -= placementDensity;

  return {
    passed: issues.length === 0,
    wordCount,
    issues,
    scores: { seo: Math.max(0, seoScore), voice: Math.max(0, voiceScore), cro: Math.max(0, croScore) },
  };
}

// ─── v2 Validator: structured errors + anchor resolution ─────────────────────

/**
 * Full hard-gate validation. Returns structured ValidatorOutput compatible with
 * the v2 pipeline types. Called by publish-service before any WP publish.
 */
export function validateArticleV2(
  article: string,
  brief: ContentBrief,
  placements: AnchoredPlacement[],
  siteKey = "techblog"
): ValidatorOutput {
  const errors: ValidatorError[] = [];
  const articleLower = article.toLowerCase();
  const typeRules = getTypeRules(brief.articleType);

  // Word count
  const word_count = article.trim().split(/\s+/).filter(Boolean).length;
  if (word_count < typeRules.minWords) {
    errors.push({
      code: "word_count_low",
      message: `Word count ${word_count} below minimum ${typeRules.minWords} for type "${typeRules.articleType}"`,
      severity: "error",
    });
  } else if (word_count > typeRules.maxWords) {
    errors.push({
      code: "word_count_high",
      message: `Word count ${word_count} exceeds maximum ${typeRules.maxWords} for type "${typeRules.articleType}"`,
      severity: "warning",
    });
  }

  // Disclosure
  const opening = article.slice(0, 300).toLowerCase();
  const hasDisclosure = brief.compliance.disclosurePhrases.some((p) => opening.includes(p.toLowerCase()));
  if (!hasDisclosure && brief.compliance.requireDisclosure) {
    errors.push({
      code: "disclosure_missing",
      message: "Missing affiliate disclosure in opening 300 characters",
      severity: "error",
    });
  }

  // Forbidden superlatives
  for (const term of brief.compliance.forbiddenSuperlatives) {
    if (articleLower.includes(term.toLowerCase())) {
      errors.push({
        code: "superlative_found",
        message: `Forbidden term found: "${term}"`,
        severity: "error",
      });
    }
  }

  // Verdict
  if (typeRules.requireVerdict && !/vores dom|konklusion|sammenfattende/i.test(article)) {
    errors.push({
      code: "verdict_missing",
      message: "Missing 'Vores dom' verdict section",
      severity: "error",
    });
  }

  // Pros/Cons
  if (typeRules.requireProsCons && !/fordele|ulemper|det vi kan lide|det vi ville ændre/i.test(article)) {
    errors.push({
      code: "pros_cons_missing",
      message: `Missing pros/cons sections (required for type "${typeRules.articleType}")`,
      severity: "error",
    });
  }

  // Product coverage
  for (const product of brief.products) {
    const shortName = product.name.slice(0, 30).toLowerCase();
    if (!articleLower.includes(shortName)) {
      errors.push({
        code: "product_missing",
        message: `Product may be missing from article: "${product.name.slice(0, 40)}"`,
        severity: "warning",
      });
    }
  }

  // Anchor resolution check
  if (placements.length > 0) {
    const { errors: anchorErrors } = insertAnchoredPlacements(article, brief, placements, siteKey);
    for (const ae of anchorErrors) {
      errors.push({ code: ae.code, message: ae.message, severity: "error" });
    }
  }

  return {
    passed: errors.filter((e) => e.severity === "error").length === 0,
    errors,
    word_count,
  };
}

// ─── Legacy validator (used by file-writer) ───────────────────────────────────

export function validateArticle(article: string, brief: ContentBrief): ValidationResult {
  const issues: string[] = [];
  let score = 1.0;

  // REQ-COMP-001: Disclosure in first 300 chars
  const opening = article.slice(0, 300).toLowerCase();
  const hasDisclosure = brief.compliance.disclosurePhrases.some((phrase) =>
    opening.includes(phrase.toLowerCase())
  );
  if (!hasDisclosure) {
    issues.push("MISSING_DISCLOSURE");
    score -= 0.3;
  }

  // REQ-COMP-002: Forbidden superlatives
  const lowerArticle = article.toLowerCase();
  for (const sup of brief.compliance.forbiddenSuperlatives) {
    if (lowerArticle.includes(sup.toLowerCase())) {
      issues.push(`FORBIDDEN_SUPERLATIVE: "${sup}"`);
      score -= 0.1;
    }
  }

  // REQ-COMP-003: Widget placeholder coverage
  for (const product of brief.products) {
    const placeholder = `{{AFFILIATE_WIDGET_${product.id}}}`;
    if (!article.includes(placeholder)) {
      issues.push(`MISSING_WIDGET_PLACEHOLDER: ${product.id}`);
      score -= 0.1;
    }
  }

  const confidence_score = Math.max(0, Math.min(1, score));
  const publish_mode: "publish" | "draft" = confidence_score >= 0.7 ? "publish" : "draft";

  return {
    confidence_score,
    issues,
    publish_mode,
    article_with_placeholders: article,
  };
}
