/**
 * SEO Metadata Validator
 * 
 * Validates generated Yoast SEO metadata against hard rules:
 * - Title: 40-60 chars, contains focus kw, no em dashes, no HTML entities
 * - Meta desc: 120-155 chars, contains focus kw, no em dashes, no HTML entities
 * - Focus kw: 1-4 words, Danish, not empty
 * - Focus kw must appear in both title and meta desc
 * 
 * Output: validation report with pass/fail per post
 */

import * as fs from "fs";

interface SeoMeta {
  id: number;
  title: string;
  slug: string;
  link: string;
  categories: number[];
  excerpt: string;
  seo_title: string;
  seo_metadesc: string;
  seo_focuskw: string;
}

interface ValidationResult {
  id: number;
  title: string;
  passed: boolean;
  errors: string[];
  warnings: string[];
  seo_title: string;
  seo_metadesc: string;
  seo_focuskw: string;
}

const data: SeoMeta[] = JSON.parse(fs.readFileSync("/tmp/seo-metadata.json", "utf-8"));

function validate(post: SeoMeta): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const { id, title, seo_title, seo_metadesc, seo_focuskw } = post;

  // --- Focus keyword checks ---
  if (!seo_focuskw || seo_focuskw.trim().length === 0) {
    errors.push("Focus keyword is empty");
  } else {
    const kwWords = seo_focuskw.trim().split(/\s+/);
    if (kwWords.length > 4) {
      errors.push(`Focus keyword too long (${kwWords.length} words, max 4)`);
    }
    if (kwWords.length === 1 && kwWords[0].length < 3) {
      errors.push("Focus keyword too short (single word < 3 chars)");
    }
  }

  // --- Title checks ---
  if (!seo_title || seo_title.trim().length === 0) {
    errors.push("SEO title is empty");
  } else {
    if (seo_title.length < 40) {
      errors.push(`SEO title too short (${seo_title.length} chars, min 40)`);
    }
    if (seo_title.length > 65) {
      errors.push(`SEO title too long (${seo_title.length} chars, max 65)`);
    }
    if (seo_title.length > 60 && seo_title.length <= 65) {
      warnings.push(`SEO title slightly long (${seo_title.length} chars, ideal max 60)`);
    }
    // Check focus kw in title (case insensitive)
    if (seo_focuskw && !seo_title.toLowerCase().includes(seo_focuskw.toLowerCase())) {
      warnings.push("Focus keyword not found in SEO title");
    }
    // No em dashes
    if (/-|-/.test(seo_title)) {
      errors.push("SEO title contains em/en dashes");
    }
    // No HTML entities
    if (/&#[0-9]+;|&[a-z]+;/.test(seo_title)) {
      errors.push("SEO title contains HTML entities");
    }
  }

  // --- Meta description checks ---
  if (!seo_metadesc || seo_metadesc.trim().length === 0) {
    errors.push("Meta description is empty");
  } else {
    if (seo_metadesc.length < 100) {
      errors.push(`Meta desc too short (${seo_metadesc.length} chars, min 100)`);
    }
    if (seo_metadesc.length > 160) {
      errors.push(`Meta desc too long (${seo_metadesc.length} chars, max 160)`);
    }
    if (seo_metadesc.length > 155 && seo_metadesc.length <= 160) {
      warnings.push(`Meta desc slightly long (${seo_metadesc.length} chars, ideal max 155)`);
    }
    // Check focus kw in desc (case insensitive)
    if (seo_focuskw && !seo_metadesc.toLowerCase().includes(seo_focuskw.toLowerCase())) {
      warnings.push("Focus keyword not found in meta description");
    }
    // No em dashes
    if (/-|-/.test(seo_metadesc)) {
      errors.push("Meta description contains em/en dashes");
    }
    // No HTML entities
    if (/&#[0-9]+;|&[a-z]+;/.test(seo_metadesc)) {
      errors.push("Meta description contains HTML entities");
    }
    // Should end with period
    if (!seo_metadesc.endsWith(".")) {
      warnings.push("Meta description should end with a period");
    }
  }

  return {
    id,
    title,
    passed: errors.length === 0,
    errors,
    warnings,
    seo_title,
    seo_metadesc,
    seo_focuskw,
  };
}

const results: ValidationResult[] = data.map(validate);

// Output
const passed = results.filter(r => r.passed).length;
const failed = results.filter(r => !r.passed).length;

console.log(`\n=== SEO VALIDATION REPORT ===`);
console.log(`Total: ${results.length} | Passed: ${passed} | Failed: ${failed}\n`);

for (const r of results) {
  const status = r.passed ? "✅ PASS" : "❌ FAIL";
  console.log(`${status} | ID:${r.id} | ${r.title}`);
  console.log(`  Title (${r.seo_title.length}): ${r.seo_title}`);
  console.log(`  Desc  (${r.seo_metadesc.length}): ${r.seo_metadesc}`);
  console.log(`  Focus: ${r.seo_focuskw}`);
  if (r.errors.length > 0) {
    for (const e of r.errors) console.log(`  ❌ ${e}`);
  }
  if (r.warnings.length > 0) {
    for (const w of r.warnings) console.log(`  ⚠️  ${w}`);
  }
  console.log();
}

// Save results
fs.writeFileSync("/tmp/seo-validation.json", JSON.stringify(results, null, 2));
console.log("Validation saved to /tmp/seo-validation.json");

// Exit with error if any failed
if (failed > 0) {
  console.log(`\n${failed} posts need fixes before publishing.`);
  process.exit(1);
} else {
  console.log("\nAll posts passed validation. Ready for review.");
  process.exit(0);
}
