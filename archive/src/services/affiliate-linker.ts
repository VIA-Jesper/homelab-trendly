import { marked } from "marked";
import type { ContentBrief } from "../types/index.js";
import { SITE_CONFIGS } from "../config/sites.js";

// ─── Markdown → HTML conversion ───────────────────────────────────────────────
/** Converts Markdown (with any pre-inserted HTML blocks) to a full HTML string */
export function convertMarkdownToHtml(markdown: string): string {
  // marked.parse is sync when no async extensions are used
  const result = marked.parse(markdown, { async: false });
  return result as string;
}

/** Extracts the text content of the first <h1> from HTML */
export function extractH1(html: string): string | undefined {
  const match = /<h1[^>]*>(.*?)<\/h1>/i.exec(html);
  if (!match) return undefined;
  // Strip any inner tags (e.g. <strong>)
  return match[1]!.replace(/<[^>]+>/g, "").trim();
}

// ─── Inline affiliate link conversion ────────────────────────────────────────

interface LinkerResult {
  html: string;
  /** Product names that had 0 mentions in the article */
  warnings: string[];
}

/**
 * Scans the HTML for product name mentions and converts them to affiliate links.
 * Rules:
 *  - Case-insensitive, word-boundary match
 *  - Max 2 links per product
 *  - Never inside <h1>-<h6> tags
 *  - Link uses rel="sponsored"
 */
/**
 * Appends ?partnerId=... to any PriceRunner href in the HTML that does not already have it.
 * Covers both explicit markdown links the generator wrote AND widget attribution links.
 */
function appendPartnerIdToPrLinks(html: string, partnerId: string): string {
  if (!partnerId) return html;
  const encoded = encodeURIComponent(partnerId);
  return html.replace(
    /href="(https?:\/\/(?:www\.)?pricerunner\.[a-z]{2,3}[^"]*)"/gi,
    (match, url: string) => {
      if (url.includes("partnerId=")) return match;
      const sep = url.includes("?") ? "&" : "?";
      return `href="${url}${sep}partnerId=${encoded}"`;
    }
  );
}

export function insertAffiliateLinks(
  html: string,
  brief: ContentBrief,
  siteKey: string
): LinkerResult {
  const siteConfig = SITE_CONFIGS[siteKey];
  const partnerId = siteConfig?.pricerunnerPartnerId ?? "";
  const warnings: string[] = [];

  let result = html;

  for (const product of brief.products) {
    const encodedPartnerId = encodeURIComponent(partnerId);
    const affiliateHref = partnerId
      ? `${product.affiliateUrl}?partnerId=${encodedPartnerId}`
      : product.affiliateUrl;

    // Escape any regex-special chars in the product name
    const escaped = product.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Word boundary around the product name, case-insensitive
    const pattern = new RegExp(`(?<![\\w>])${escaped}(?![\\w<])`, "gi");

    let matchCount = 0;
    let totalMatches = 0;

    // First pass: count total matches outside headings to detect 0-mention products
    const testHtml = stripHeadings(result);
    const allMatches = testHtml.match(pattern);
    totalMatches = allMatches?.length ?? 0;

    if (totalMatches === 0) {
      warnings.push(product.name);
      continue;
    }

    // Second pass: replace up to 2 matches, skipping headings and tags
    result = replaceOutsideTagsAndHeadings(result, pattern, (match) => {
      if (matchCount >= 2) return match;
      matchCount++;
      return `<a href="${affiliateHref}" rel="sponsored">${match}</a>`;
    });
  }

  // Final pass: stamp partnerId on any PriceRunner link the generator wrote explicitly
  // (links already inside <a> tags are skipped by replaceOutsideTagsAndHeadings, so we handle them here)
  result = appendPartnerIdToPrLinks(result, partnerId);

  return { html: result, warnings };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Returns the HTML with heading tag content blanked out (for counting body mentions) */
function stripHeadings(html: string): string {
  return html.replace(/<h[1-6][^>]*>.*?<\/h[1-6]>/gis, "");
}

/**
 * Applies a replacer function to regex matches in `html`,
 * but skips matches that fall inside heading tags OR inside any HTML tag (attributes).
 */
function replaceOutsideTagsAndHeadings(
  html: string,
  pattern: RegExp,
  replacer: (match: string) => string
): string {
  // Split by tags: <...>
  const parts = html.split(/(<[^>]+>)/g);
  let inHeading = false;
  let inLink = false;

  return parts
    .map((part) => {
      // If it's a tag, check if it's a heading or anchor tag and return it untouched
      if (part.startsWith("<") && part.endsWith(">")) {
        if (/<h[1-6]/i.test(part)) inHeading = true;
        if (/<\/h[1-6]/i.test(part)) inHeading = false;
        if (/<a\b/i.test(part)) inLink = true;
        if (/<\/a>/i.test(part)) inLink = false;
        return part;
      }
      // If we are inside a heading or already inside a link, skip replacement
      if (inHeading || inLink) return part;
      // Otherwise, replace in the text node
      return part.replace(pattern, replacer);
    })
    .join("");
}
