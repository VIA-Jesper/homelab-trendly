import { describe, it, expect } from "vitest";
import { classifyProducts } from "../../src/services/article-classifier.js";
import type { RawProduct } from "../../src/services/product-store.js";

// ─── Fixture helpers ──────────────────────────────────────────────────────────

function makeProduct(overrides: Partial<RawProduct> = {}): RawProduct {
  return {
    id: "pr_1",
    name: "Test Product",
    category: "elsave",
    priceKr: 1000,
    retailer: "TestShop",
    affiliateUrl: "https://www.pricerunner.dk/pl/1",
    imageUrl: "https://cdn.pricerunner.dk/img/1.jpg",
    popularityScore: 10,
    outOfStock: false,
    specs: {},
    ...overrides,
  };
}

function withWatchers(p: Partial<RawProduct>, label = "200+"): Partial<RawProduct> {
  return { ...p, specs: { ...p.specs, watchedLabel: label } };
}

function withRankOne(p: Partial<RawProduct>): Partial<RawProduct> {
  return { ...p, specs: { ...p.specs, popularityRank: "1" } };
}

function withPriceDrop(p: Partial<RawProduct>, pct = "18%"): Partial<RawProduct> {
  return { ...p, specs: { ...p.specs, priceDrop: pct } };
}

function withBrand(p: Partial<RawProduct>, brand: string): Partial<RawProduct> {
  return { ...p, specs: { ...p.specs, brand } };
}

// ─── hero ─────────────────────────────────────────────────────────────────────

describe("classifyProducts - hero", () => {
  it("classifies as hero when top score ≥ 2× second and has watchers", () => {
    const products = [
      makeProduct({ ...withWatchers(withRankOne({})), popularityScore: 80 }),
      makeProduct({ id: "pr_2", popularityScore: 30 }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("hero");
  });

  it("classifies as hero when only one product with watchers", () => {
    const products = [makeProduct(withWatchers({ popularityScore: 50 }))];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("hero");
  });

  it("hero hook contains product name", () => {
    const products = [makeProduct({ ...withWatchers(withRankOne({})), popularityScore: 80, name: "Makita DSP600Z" })];
    const { articleHook } = classifyProducts(products);
    expect(articleHook).toContain("Makita DSP600Z");
  });

  it("hero hook references watcher label when present", () => {
    const products = [makeProduct({ ...withWatchers({}, "200+"), popularityScore: 80, name: "Makita" })];
    const { articleHook } = classifyProducts(products);
    expect(articleHook).toContain("200+");
  });

  it("does NOT classify as hero when scores are close", () => {
    const products = [
      makeProduct({ ...withWatchers(withRankOne({})), popularityScore: 50 }),
      makeProduct({ id: "pr_2", popularityScore: 40 }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).not.toBe("hero");
  });
});

// ─── deal ─────────────────────────────────────────────────────────────────────

describe("classifyProducts - deal", () => {
  it("classifies as deal when priceDrop ≥ 10% and has watchers", () => {
    const products = [
      makeProduct({ ...withWatchers(withPriceDrop({})), popularityScore: 50 }),
      makeProduct({ id: "pr_2", popularityScore: 45 }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("deal");
  });

  it("deal hook includes price drop percentage", () => {
    // Two similar-scoring products so hero doesn't fire, but top has priceDrop + watchers
    const products = [
      makeProduct({ ...withWatchers(withPriceDrop({}, "22%")), popularityScore: 50 }),
      makeProduct({ id: "pr_2", popularityScore: 45 }),
    ];
    const { articleHook } = classifyProducts(products);
    expect(articleHook).toContain("22%");
  });

  it("does NOT classify as deal when priceDrop < 10%", () => {
    const products = [makeProduct({ ...withWatchers(withPriceDrop({}, "5%")), popularityScore: 50 })];
    const { articleType } = classifyProducts(products);
    expect(articleType).not.toBe("deal");
  });

  it("does NOT classify as deal without watchers", () => {
    const products = [makeProduct(withPriceDrop({ popularityScore: 50 }))];
    const { articleType } = classifyProducts(products);
    expect(articleType).not.toBe("deal");
  });
});

// ─── brand-vs-brand ───────────────────────────────────────────────────────────

describe("classifyProducts - brand-vs-brand", () => {
  it("classifies as brand-vs-brand when two different brands have close scores", () => {
    const products = [
      makeProduct({ ...withBrand({}, "Makita"), popularityScore: 50, id: "pr_1" }),
      makeProduct({ ...withBrand({}, "Bosch"), popularityScore: 45, id: "pr_2" }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("brand-vs-brand");
  });

  it("brand-vs-brand hook names both brands", () => {
    const products = [
      makeProduct({ ...withBrand({}, "Makita"), popularityScore: 50, id: "pr_1" }),
      makeProduct({ ...withBrand({}, "Bosch"), popularityScore: 45, id: "pr_2" }),
    ];
    const { articleHook } = classifyProducts(products);
    expect(articleHook).toContain("Makita");
    expect(articleHook).toContain("Bosch");
  });

  it("does NOT classify as brand-vs-brand when same brand", () => {
    const products = [
      makeProduct({ ...withBrand({}, "Makita"), popularityScore: 50, id: "pr_1" }),
      makeProduct({ ...withBrand({}, "Makita"), popularityScore: 48, id: "pr_2" }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).not.toBe("brand-vs-brand");
  });
});

// ─── budget-tiers ─────────────────────────────────────────────────────────────

describe("classifyProducts - budget-tiers", () => {
  it("classifies as budget-tiers when 3+ products and max ≥ 2× min price", () => {
    const products = [
      makeProduct({ id: "pr_1", priceKr: 3000, popularityScore: 20 }),
      makeProduct({ id: "pr_2", priceKr: 6000, popularityScore: 15 }),
      makeProduct({ id: "pr_3", priceKr: 1000, popularityScore: 10 }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("budget-tiers");
  });

  it("budget-tiers hook contains min and max prices", () => {
    const products = [
      makeProduct({ id: "pr_1", priceKr: 3000, popularityScore: 20 }),
      makeProduct({ id: "pr_2", priceKr: 6000, popularityScore: 15 }),
      makeProduct({ id: "pr_3", priceKr: 1000, popularityScore: 10 }),
    ];
    const { articleHook } = classifyProducts(products);
    expect(articleHook).toContain("1.000 kr.");
    expect(articleHook).toContain("6.000 kr.");
  });
});

// ─── roundup ─────────────────────────────────────────────────────────────────

describe("classifyProducts - roundup", () => {
  it("defaults to roundup when no pattern matches", () => {
    const products = [
      makeProduct({ id: "pr_1", popularityScore: 15 }),
      makeProduct({ id: "pr_2", popularityScore: 14 }),
    ];
    const { articleType } = classifyProducts(products);
    expect(articleType).toBe("roundup");
  });

  it("returns roundup for empty array", () => {
    const { articleType, articleHook } = classifyProducts([]);
    expect(articleType).toBe("roundup");
    expect(articleHook.length).toBeGreaterThan(0);
  });

  it("roundup hook mentions category", () => {
    const products = [
      makeProduct({ category: "elsave", popularityScore: 10, id: "pr_1" }),
      makeProduct({ category: "elsave", popularityScore: 9, id: "pr_2" }),
    ];
    const { articleType, articleHook } = classifyProducts(products);
    expect(articleType).toBe("roundup");
    expect(articleHook).toContain("elsave");
  });
});

// ─── determinism ─────────────────────────────────────────────────────────────

describe("classifyProducts - determinism", () => {
  it("returns identical output on repeated calls with same input", () => {
    const products = [
      makeProduct({ ...withWatchers(withRankOne({})), popularityScore: 80 }),
      makeProduct({ id: "pr_2", popularityScore: 30 }),
    ];
    const first = classifyProducts(products);
    const second = classifyProducts(products);
    expect(first.articleType).toBe(second.articleType);
    expect(first.articleHook).toBe(second.articleHook);
  });
});
