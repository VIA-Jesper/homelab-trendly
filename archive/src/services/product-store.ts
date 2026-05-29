import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import type { ProductBrief } from "../types/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DATA_PATH = join(__dirname, "../../data/products.json");

// RawProduct includes internal fields not exposed in ProductBrief
export interface RawProduct extends ProductBrief {
  imageUrl: string;
  /** Pre-computed popularity score from PriceRunner signals (watchers, rank, rating, merchants) */
  popularityScore: number;
  /** True if the product is out of stock across all merchants */
  outOfStock: boolean;
}

let _cache: RawProduct[] | null = null;

function loadProducts(): RawProduct[] {
  if (_cache) return _cache;
  if (!existsSync(DATA_PATH)) {
    throw new Error(
      "data/products.json not found. Run `npm run seed` to populate it from PriceRunner."
    );
  }
  const raw = readFileSync(DATA_PATH, "utf-8");
  _cache = JSON.parse(raw) as RawProduct[];
  return _cache;
}

export function getProductsByCategory(category: string): RawProduct[] {
  return loadProducts()
    .filter((p) => p.category.toLowerCase() === category.toLowerCase())
    .filter((p) => !p.outOfStock)
    .sort((a, b) => (b.popularityScore ?? 0) - (a.popularityScore ?? 0))
    .slice(0, 5);
}

export function getProductByUrl(productUrl: string): RawProduct | undefined {
  return loadProducts().find((p) => p.affiliateUrl === productUrl);
}

export function getImageUrl(productId: string): string {
  const product = loadProducts().find((p) => p.id === productId);
  return product?.imageUrl ?? "";
}
