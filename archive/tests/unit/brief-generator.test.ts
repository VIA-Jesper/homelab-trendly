import { describe, it, expect, vi, beforeEach } from "vitest";
import type { RawProduct } from "../../src/services/product-store.js";

// ─── Mock dependencies ────────────────────────────────────────────────────────

const mockProducts: RawProduct[] = [
  {
    id: "pr_1",
    name: "Makita DSP600Z",
    category: "elsave",
    priceKr: 3499,
    retailer: "Bilka",
    affiliateUrl: "https://www.pricerunner.dk/pl/1",
    imageUrl: "https://cdn.pricerunner.dk/img/1.jpg",
    popularityScore: 80,
    outOfStock: false,
    specs: { brand: "Makita", watchedLabel: "200+", popularityRank: "1" },
  },
  {
    id: "pr_2",
    name: "Bosch GKS 18V",
    category: "elsave",
    priceKr: 2899,
    retailer: "Power",
    affiliateUrl: "https://www.pricerunner.dk/pl/2",
    imageUrl: "https://cdn.pricerunner.dk/img/2.jpg",
    popularityScore: 35,
    outOfStock: false,
    specs: { brand: "Bosch" },
  },
];

vi.mock("../../src/services/product-store.js", () => ({
  getProductsByCategory: vi.fn(() => mockProducts),
  getProductByUrl: vi.fn(() => undefined),
  getImageUrl: vi.fn(() => "https://cdn.pricerunner.dk/img/fallback.jpg"),
  getUsedProductIds: vi.fn(() => []),
}));

vi.mock("../../src/config/sites.js", () => ({
  SITE_CONFIGS: {},
}));

vi.mock("../../src/services/content-registry.js", () => ({
  getUsedProductIds: vi.fn(() => []),
}));

vi.mock("../../src/services/category-traversal.js", () => ({
  getMostUnwrittenLeafCategory: vi.fn(() => null),
  getFreshProductsForCategory: vi.fn(() => null),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("generateBrief - article classification", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("includes articleType in returned brief", async () => {
    const { generateBrief } = await import("../../src/services/brief-generator.js");
    const brief = generateBrief("elsave", undefined, "techblog");
    expect(brief.articleType).toBeDefined();
    expect(["hero", "deal", "brand-vs-brand", "budget-tiers", "roundup"]).toContain(brief.articleType);
  });

  it("includes non-empty articleHook in returned brief", async () => {
    const { generateBrief } = await import("../../src/services/brief-generator.js");
    const brief = generateBrief("elsave", undefined, "techblog");
    expect(brief.articleHook).toBeDefined();
    expect(brief.articleHook!.length).toBeGreaterThan(0);
  });

  it("classifies dominant product as hero", async () => {
    const { generateBrief } = await import("../../src/services/brief-generator.js");
    // mockProducts[0] has score 80 ≥ 2× 35, has watchers and rank 1 → hero
    const brief = generateBrief("elsave", undefined, "techblog");
    expect(brief.articleType).toBe("hero");
  });

  it("strips imageUrl, popularityScore, outOfStock from products in brief", async () => {
    const { generateBrief } = await import("../../src/services/brief-generator.js");
    const brief = generateBrief("elsave", undefined, "techblog");
    for (const p of brief.products) {
      expect(p).not.toHaveProperty("imageUrl");
      expect(p).not.toHaveProperty("popularityScore");
      expect(p).not.toHaveProperty("outOfStock");
    }
  });

  it("brief still contains all required base fields", async () => {
    const { generateBrief } = await import("../../src/services/brief-generator.js");
    const brief = generateBrief("elsave", undefined, "techblog");
    expect(brief.brief_id).toBeDefined();
    expect(brief.category).toBe("elsave");
    expect(brief.products.length).toBeGreaterThan(0);
    expect(brief.images.length).toBeGreaterThan(0);
    expect(brief.writing_rules).toBeDefined();
    expect(brief.compliance).toBeDefined();
  });
});
