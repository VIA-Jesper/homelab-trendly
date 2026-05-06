import { writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import type { ContentBrief, PublishResult, ValidationResult } from "../types/index.js";

const OUTPUT_ROOT = "output";

interface WriteOptions {
  jobId: string;
  article: string;
  brief: ContentBrief;
  validation: ValidationResult;
}

export function writeArticleToFile({ jobId, article, brief, validation }: WriteOptions): PublishResult {
  const dir = join(OUTPUT_ROOT, jobId);
  mkdirSync(dir, { recursive: true });

  // 1. article.html — final HTML with widgets already inserted
  const articlePath = join(dir, "article.html");
  writeFileSync(articlePath, wrapHtml(article, brief.category), "utf-8");

  // 2. report.json — validation metadata for review
  const report = {
    job_id: jobId,
    brief_id: brief.brief_id,
    category: brief.category,
    confidence_score: validation.confidence_score,
    publish_mode: validation.publish_mode,
    issues: validation.issues,
    savedAt: new Date().toISOString(),
  };
  writeFileSync(join(dir, "report.json"), JSON.stringify(report, null, 2), "utf-8");

  console.log(`[file-writer] Saved → ${articlePath}`);
  return { status: "saved", filePath: articlePath };
}

function wrapHtml(content: string, category: string): string {
  const title = `${category.charAt(0).toUpperCase() + category.slice(1)} — Trendly Guide`;
  return `<!DOCTYPE html>
<html lang="da">
<head>
  <meta charset="UTF-8">
  <title>${title}</title>
  <style>
    body { font-family: sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; }
    .trendly-affiliate-widget { border: 1px solid #ddd; border-radius: 6px; padding: 1rem; margin: 1.5rem 0; }
    .taw-name { font-weight: bold; font-size: 1.1rem; }
    .taw-price { color: #c00; font-size: 1.2rem; margin: 0.25rem 0; }
    .taw-cta { display: inline-block; margin-top: 0.5rem; padding: 0.5rem 1rem;
               background: #0066cc; color: white; border-radius: 4px; text-decoration: none; }
  </style>
</head>
<body>
${content}
</body>
</html>`;
}
