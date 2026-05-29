import axios from "axios";
import type { ContentBrief, PublishResult, SeoPayload, Placement, AnchoredPlacement } from "../types/index.js";
import { SITE_CONFIGS } from "../config/sites.js";
import { insertPlacements, insertAnchoredPlacements } from "./widget-inserter.js";
import { convertMarkdownToHtml, extractH1, insertAffiliateLinks } from "./affiliate-linker.js";
import { registerProducts } from "./content-registry.js";
import { withBackoff } from "../scraper/pricerunner-client.js";

// ─── Slug generation with Danish transliteration ─────────────────────────────
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/æ/g, "ae")
    .replace(/ø/g, "oe")
    .replace(/å/g, "aa")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

// ─── WP category resolution ───────────────────────────────────────────────────
export function resolveWpCategory(siteKey: string, briefCategory: string): number {
  const siteConfig = SITE_CONFIGS[siteKey];
  if (!siteConfig) throw new Error(`Unknown site key: ${siteKey}`);
  return siteConfig.categoryMap[briefCategory.toLowerCase()] ?? siteConfig.categoryId;
}

// ─── Publisher options ────────────────────────────────────────────────────────
export interface PublishOptions {
  jobId: string;
  article: string;           // raw Markdown from agent
  brief: ContentBrief;
  siteKey: string;
  status: "publish" | "draft";
  /** @deprecated Use anchoredPlacements. Kept for backward compat. */
  placements?: Placement[];
  anchoredPlacements?: AnchoredPlacement[];
  seo?: SeoPayload;
}

// ─── Main publisher ───────────────────────────────────────────────────────────
export async function publishToWordPress(options: PublishOptions): Promise<PublishResult> {
  const { jobId, article, brief, siteKey, status, placements, anchoredPlacements, seo } = options;
  const siteConfig = SITE_CONFIGS[siteKey];
  if (!siteConfig) throw new Error(`Unknown site key: ${siteKey}`);

  const { username, appPassword, baseUrl } = siteConfig;
  if (!username || !appPassword) {
    throw new Error(`WordPress credentials missing for site "${siteKey}". Set WP_${siteKey.toUpperCase()}_USER and WP_${siteKey.toUpperCase()}_APP_PASSWORD env vars.`);
  }

  // 1. Inject agent-directed placements into Markdown
  // v2: prefer anchored placements; fall back to legacy paragraph-index placements
  let articleWithPlacements: string;
  if (anchoredPlacements && anchoredPlacements.length > 0) {
    const { html } = insertAnchoredPlacements(article, brief, anchoredPlacements, siteKey);
    articleWithPlacements = html;
  } else {
    articleWithPlacements = insertPlacements(article, brief, placements ?? [], siteKey);
  }

  // 2. Convert Markdown + HTML blocks → full HTML
  const rawHtml = convertMarkdownToHtml(articleWithPlacements);

  // 3. Run inline affiliate link conversion
  const { html: finalHtml, warnings } = insertAffiliateLinks(rawHtml, brief, siteKey);

  // 4. Resolve SEO fields
  const h1 = extractH1(finalHtml);
  const title = seo?.title ?? h1 ?? brief.category;
  const slug = seo?.slug ? slugify(seo.slug) : slugify(h1 ?? brief.category);
  const wpCategoryId = resolveWpCategory(siteKey, brief.category);

  // 5. Build WP REST API post body
  const meta: Record<string, string> = {};
  meta["rank_math_title"] = title;
  if (seo?.description) meta["rank_math_description"] = seo.description;
  if (seo?.focus_keyword) meta["rank_math_focus_keyword"] = seo.focus_keyword;

  const postBody: Record<string, unknown> = {
    title,
    content: finalHtml,
    status,
    slug,
    categories: [wpCategoryId],
    meta,
  };

  // 6. POST to WordPress
  const endpoint = `${baseUrl}/wp-json/wp/v2/posts`;
  const credentials = Buffer.from(`${username}:${appPassword}`).toString("base64");

  let wpResponse: { id: number; link: string };
  try {
    wpResponse = await withBackoff(async () => {
      const res = await axios.post<{ id: number; link: string }>(endpoint, postBody, {
        headers: {
          Authorization: `Basic ${credentials}`,
          "Content-Type": "application/json",
        },
        timeout: 30_000,
      });
      return res.data;
    });
  } catch (err: unknown) {
    if (axios.isAxiosError(err) && err.response?.status === 401) {
      throw new Error(`wp_auth_failed:${siteKey}`);
    }
    throw new Error(`wp_publish_failed:${siteKey}`);
  }

  // 7. Update content registry for published (not draft) articles
  if (status === "publish") {
    const productIds = brief.products.map((p) => p.id);
    registerProducts(siteKey, productIds);
  }

  console.log(`[wp-publisher] ${status === "publish" ? "Published" : "Drafted"} → ${wpResponse.link} (job: ${jobId})`);

  return {
    status: status === "publish" ? "published" : "draft",
    wp_post_id: wpResponse.id,
    url: wpResponse.link,
    site: siteKey,
    warnings,
  };
}
