import { v4 as uuidv4 } from "uuid";
import type { ContentBrief, ImageRef, WritingRules, ComplianceRules } from "../types/index.js";
import { getProductsByCategory, getProductByUrl, getImageUrl } from "./product-store.js";
import { SITE_CONFIGS } from "../config/sites.js";

const DEFAULT_WRITING_RULES: WritingRules = {
  tone: "neutral", minWords: 600, maxWords: 1200,
  includeProsCons: true, includeVerdict: true,
};

const DEFAULT_COMPLIANCE: ComplianceRules = {
  requireDisclosure: true,
  disclosurePhrases: [
    "indeholder affiliatelinks", "vi tjener kommission", "annonce", "reklame",
  ],
  forbiddenSuperlatives: [
    "bedste på markedet", "billigst i danmark", "nr. 1 valg", "absolut bedst",
  ],
};

export function generateBrief(
  category: string | undefined,
  productUrl: string | undefined,
  siteKey = "techblog"
): ContentBrief {
  const siteConfig = SITE_CONFIGS[siteKey];
  const writingRules = siteConfig?.writingRules ?? DEFAULT_WRITING_RULES;

  let products;
  let resolvedCategory: string;

  if (productUrl) {
    const single = getProductByUrl(productUrl);
    products = single ? [single] : [];
    resolvedCategory = single?.category ?? "unknown";
  } else {
    resolvedCategory = category ?? "general";
    products = getProductsByCategory(resolvedCategory);
  }

  const images: ImageRef[] = products.map((p) => ({
    productId: p.id,
    url: getImageUrl(p.id),
    alt: `${p.name} — ${Object.values(p.specs).slice(0, 2).join(", ")}`,
    caption: `${p.name} hos ${p.retailer} — ${p.priceKr.toLocaleString("da-DK")} kr.`,
  }));

  return {
    brief_id: uuidv4(),
    category: resolvedCategory,
    // Strip internal imageUrl field before returning ProductBrief
    products: products.map(({ imageUrl: _omit, ...rest }) => rest),
    images,
    writing_rules: writingRules,
    compliance: DEFAULT_COMPLIANCE,
  };
}
