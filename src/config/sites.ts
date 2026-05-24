import type { SiteConfig, WritingRules } from "../types/index.js";

const DEFAULT_RULES: WritingRules = {
  tone: "neutral", minWords: 600, maxWords: 1200,
  includeProsCons: true, includeVerdict: true,
};

/** Load WP credentials from env vars for a site key (e.g. "techblog" -> WP_TECHBLOG_USER) */
function wpCredentials(siteKey: string): { username: string; appPassword: string } {
  const upper = siteKey.toUpperCase();
  return {
    username: process.env[`WP_${upper}_USER`] ?? "",
    appPassword: process.env[`WP_${upper}_APP_PASSWORD`] ?? "",
  };
}

export const SITE_CONFIGS: Record<string, SiteConfig> = {
  techblog: {
    baseUrl: process.env["WP_TECHBLOG_BASE_URL"] ?? "https://techblog.example.dk",
    ...wpCredentials("techblog"),
    defaultStatus: "publish",
    categoryId: 5,
    writingRules: { ...DEFAULT_RULES, tone: "analytical", minWords: 800, maxWords: 1400 },
    pricerunnerCountry: "DK",
    pricerunnerCategories: ["27", "94", "1", "2"],
    pricerunnerPartnerId: process.env["PR_TECHBLOG_PARTNER_ID"] ?? "",
    categoryMap: {
      laptops: 5,
      headphones: 6,
      phones: 7,
      tvs: 8,
    },
  },
  budgetshop: {
    baseUrl: process.env["WP_BUDGETSHOP_BASE_URL"] ?? "https://budgetshop.example.dk",
    ...wpCredentials("budgetshop"),
    defaultStatus: "publish",
    categoryId: 3,
    writingRules: { ...DEFAULT_RULES, tone: "friendly", minWords: 500, maxWords: 900 },
    pricerunnerCountry: "DK",
    pricerunnerCategories: ["27", "94"],
    pricerunnerPartnerId: process.env["PR_BUDGETSHOP_PARTNER_ID"] ?? "",
    categoryMap: {
      laptops: 3,
      headphones: 4,
    },
  },
  husforbegyndere: {
    baseUrl: process.env["WP_HUS_URL"] ?? "https://husforbegyndere.dk",
    ...{ username: process.env["WP_HUS_USER"] ?? "", appPassword: process.env["WP_HUS_PASS"] ?? "" },
    defaultStatus: "publish",
    categoryId: 12,
    writingRules: { ...DEFAULT_RULES, tone: "neutral", minWords: 700, maxWords: 1300 },
    pricerunnerCountry: "DK",
    pricerunnerCategories: ["82", "1613", "120", "335", "638"],
    pricerunnerPartnerId: process.env["PR_HUS_PARTNER_ID"] ?? "",
    categoryMap: {
      kaffemaskiner: 12,
      robotstoevsugere: 12,
      havemaskiner: 13,
      grill: 13,
      hojtryksrensere: 13,
    },
  },
};
