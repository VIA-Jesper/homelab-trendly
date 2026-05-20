import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const CONFIG_PATH = join(__dirname, "../../config/article-types.json");

// ─── Raw config types ─────────────────────────────────────────────────────────

interface CroWeights {
  verdictAffiliate: number;
  placementDensity: number;
}

interface RawTypeConfig {
  minWords: number;
  maxWords: number;
  minWordsPerProductSection?: number;
  requireVerdict: boolean;
  requireProsCons: boolean;
  extraAiTells: string[];
  croWeights: CroWeights;
}

interface ArticleTypesConfig {
  commonAiTells: string[];
  types: Record<string, RawTypeConfig>;
  defaults: { scoreThreshold: number };
}

// ─── Public type ──────────────────────────────────────────────────────────────

export interface TypeRules {
  articleType: string;
  minWords: number;
  maxWords: number;
  /** 0 means "not applicable" (hero, deal, etc.) */
  minWordsPerProductSection: number;
  requireVerdict: boolean;
  requireProsCons: boolean;
  /** Merged: commonAiTells + type-specific extraAiTells */
  aiTells: string[];
  croWeights: CroWeights;
  scoreThreshold: number;
}

// ─── Module-level cache ───────────────────────────────────────────────────────

let _config: ArticleTypesConfig | null = null;

function loadConfig(): ArticleTypesConfig {
  if (_config) return _config;
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(`[article-type-config] Missing config file at ${CONFIG_PATH}`);
  }
  _config = JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as ArticleTypesConfig;
  return _config;
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Returns merged validation rules for the given article type.
 * Falls back to "roundup" if the type is unknown or undefined.
 */
export function getTypeRules(articleType: string | undefined): TypeRules {
  const config = loadConfig();
  const type = articleType && config.types[articleType] ? articleType : "roundup";
  const raw = config.types[type] ?? config.types["roundup"]!;

  return {
    articleType: type,
    minWords: raw.minWords,
    maxWords: raw.maxWords,
    minWordsPerProductSection: raw.minWordsPerProductSection ?? 0,
    requireVerdict: raw.requireVerdict,
    requireProsCons: raw.requireProsCons,
    aiTells: [...config.commonAiTells, ...raw.extraAiTells],
    croWeights: raw.croWeights,
    scoreThreshold: config.defaults.scoreThreshold,
  };
}

/**
 * Returns all supported article type keys from the config.
 */
export function getSupportedTypes(): string[] {
  return Object.keys(loadConfig().types);
}
