import type { ContentBrief, ValidationResult } from "../types/index.js";

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
