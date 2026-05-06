import type { SiteConfig, WritingRules } from "../types/index.js";

const DEFAULT_RULES: WritingRules = {
  tone: "neutral", minWords: 600, maxWords: 1200,
  includeProsCons: true, includeVerdict: true,
};

export const SITE_CONFIGS: Record<string, SiteConfig> = {
  techblog: {
    baseUrl: "https://techblog.example.dk",       // Phase 2: move to env var
    username: "",
    appPassword: "",
    defaultStatus: "publish",
    categoryId: 5,
    writingRules: { ...DEFAULT_RULES, tone: "analytical", minWords: 800, maxWords: 1400 },
  },
  budgetshop: {
    baseUrl: "https://budgetshop.example.dk",     // Phase 2: move to env var
    username: "",
    appPassword: "",
    defaultStatus: "publish",
    categoryId: 3,
    writingRules: { ...DEFAULT_RULES, tone: "friendly", minWords: 500, maxWords: 900 },
  },
};
