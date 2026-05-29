import type { RawProduct } from "./product-store.js";
import type { ArticleClassification, ArticleType } from "../types/index.js";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getWatchedLabel(p: RawProduct): string | undefined {
  return p.specs["watchedLabel"];
}

function getPriceDrop(p: RawProduct): number {
  const raw = p.specs["priceDrop"]; // e.g. "18%"
  if (!raw) return 0;
  return parseFloat(raw);
}

function getBrand(p: RawProduct): string {
  return p.specs["brand"] ?? "";
}

function hasRankOne(p: RawProduct): boolean {
  return p.specs["popularityRank"] === "1";
}

function formatPrice(kr: number): string {
  return kr.toLocaleString("da-DK") + " kr.";
}

// ─── Hook generators ─────────────────────────────────────────────────────────

function heroHook(top: RawProduct): string {
  const watched = getWatchedLabel(top);
  if (watched) {
    return `${top.name}: ${watched} overvåger aktivt prisen på dette produkt`;
  }
  return `${top.name}: det mest populære valg i kategorien lige nu`;
}

function dealHook(top: RawProduct): string {
  const drop = top.specs["priceDrop"] ?? "";
  const watched = getWatchedLabel(top);
  if (watched) {
    return `${top.name} er faldet ${drop} i pris, og ${watched} holder stadig øje med den`;
  }
  return `${top.name} er netop faldet ${drop} i pris`;
}

function brandVsBrandHook(a: RawProduct, b: RawProduct): string {
  const brandA = getBrand(a);
  const brandB = getBrand(b);
  const category = a.category;
  if (brandA && brandB) {
    return `${brandA} eller ${brandB}: hvilken ${category} er den bedste?`;
  }
  return `${a.name} eller ${b.name}: hvad er det bedste valg?`;
}

function budgetTiersHook(products: RawProduct[]): string {
  const prices = products.map((p) => p.priceKr).filter((p) => p > 0);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const category = products[0]?.category ?? "produkter";
  return `De bedste ${category} til alle budgetter. Fra ${formatPrice(min)} til ${formatPrice(max)}`;
}

function roundupHook(products: RawProduct[]): string {
  const category = products[0]?.category ?? "produkter";
  return `De bedste ${category} i 2025`;
}

// ─── Classification rules (checked in priority order) ─────────────────────────

function isSingleProductReview(products: RawProduct[]): boolean {
  if (products.length !== 1) return false;
  const p = products[0]!;
  // Only single-product-review if no hero/deal signals
  return !getWatchedLabel(p) && !hasRankOne(p) && getPriceDrop(p) < 10;
}

function isHero(products: RawProduct[]): boolean {
  if (products.length === 0) return false;
  const top = products[0]!;
  const hasSignal = !!getWatchedLabel(top) || hasRankOne(top);
  if (!hasSignal) return false;
  if (products.length === 1) return true;
  const second = products[1]!;
  return top.popularityScore >= second.popularityScore * 2;
}

function isDeal(products: RawProduct[]): boolean {
  if (products.length === 0) return false;
  const top = products[0]!;
  return getPriceDrop(top) >= 10 && !!getWatchedLabel(top);
}

function isBrandVsBrand(products: RawProduct[]): boolean {
  if (products.length < 2) return false;
  const [a, b] = [products[0]!, products[1]!];
  const brandA = getBrand(a);
  const brandB = getBrand(b);
  if (!brandA || !brandB || brandA === brandB) return false;
  const higher = Math.max(a.popularityScore, b.popularityScore);
  const lower = Math.min(a.popularityScore, b.popularityScore);
  // within 20%: lower >= higher * 0.8
  return higher === 0 || lower >= higher * 0.8;
}

function isBudgetTiers(products: RawProduct[]): boolean {
  if (products.length < 3) return false;
  const prices = products.map((p) => p.priceKr).filter((p) => p > 0);
  if (prices.length < 3) return false;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  return min > 0 && max >= min * 2;
}

// ─── Main classifier ─────────────────────────────────────────────────────────

export function classifyProducts(products: RawProduct[]): ArticleClassification {
  if (products.length === 0) {
    return { articleType: "roundup", articleHook: "De bedste produkter i 2025" };
  }

  let articleType: ArticleType;
  let articleHook: string;

  // Priority order: single-product-review → hero → deal → brand-vs-brand → budget-tiers → roundup
  if (isSingleProductReview(products)) {
    articleType = "single-product-review";
    articleHook = `${products[0]!.name}: vores fulde anmeldelse`;
  } else if (isHero(products)) {
    articleType = "hero";
    articleHook = heroHook(products[0]!);
  } else if (isDeal(products)) {
    articleType = "deal";
    articleHook = dealHook(products[0]!);
  } else if (isBrandVsBrand(products)) {
    articleType = "brand-vs-brand";
    articleHook = brandVsBrandHook(products[0]!, products[1]!);
  } else if (isBudgetTiers(products)) {
    articleType = "budget-tiers";
    articleHook = budgetTiersHook(products);
  } else {
    articleType = "roundup";
    articleHook = roundupHook(products);
  }

  return { articleType, articleHook };
}
