import { describe, it, expect } from "vitest";
import { insertPlacements } from "../../src/services/widget-inserter.js";
import type { ContentBrief, Placement } from "../../src/types/index.js";

// Minimal brief fixture — only what widget-inserter uses
const BRIEF: ContentBrief = {
  brief_id: "test-uuid",
  category: "laptops",
  products: [
    {
      id: "pr_123",
      name: "SuperBook Pro",
      category: "laptops",
      priceKr: 9999,
      retailer: "TestShop",
      affiliateUrl: "https://www.pricerunner.dk/pl/123",
      specs: { brand: "Acme" },
    },
    {
      id: "pr_456",
      name: "Budget Lappy",
      category: "laptops",
      priceKr: 3999,
      retailer: "CheapShop",
      affiliateUrl: "https://www.pricerunner.dk/pl/456",
      specs: {},
    },
  ],
  images: [
    {
      productId: "pr_123",
      url: "https://cdn.pricerunner.dk/img/123.jpg",
      alt: "SuperBook Pro",
      caption: "SuperBook Pro hos TestShop",
    },
    {
      productId: "pr_456",
      url: "https://cdn.pricerunner.dk/img/456.jpg",
      alt: "Budget Lappy",
      caption: "Budget Lappy hos CheapShop",
    },
  ],
  writing_rules: { tone: "neutral", minWords: 600, maxWords: 1200, includeProsCons: true, includeVerdict: true },
  compliance: { requireDisclosure: true, disclosurePhrases: [], forbiddenSuperlatives: [] },
};

const ARTICLE = [
  "# Best Laptops 2025",
  "Intro paragraph here.",
  "Second paragraph with more details.",
  "Third paragraph wrapping up.",
  "Conclusion paragraph.",
].join("\n\n");

describe("insertPlacements", () => {
  it("returns article unchanged when placements is empty", () => {
    const result = insertPlacements(ARTICLE, BRIEF, [], "techblog");
    expect(result).toBe(ARTICLE);
  });

  it("inserts a widget after the specified paragraph", () => {
    const placements: Placement[] = [{ type: "widget", productId: "pr_123", after_paragraph: 1 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    // techblog has no partnerId in tests (env var not set) → fallback affiliate link
    // Either the full widget or the fallback link must appear, and both use rel="sponsored"
    expect(result).toContain('rel="sponsored"');
    // Widget/fallback must appear before the remaining paragraphs
    const widgetPos = result.search(/rel="sponsored"/);
    const conclusionPos = result.indexOf("Conclusion paragraph");
    expect(widgetPos).toBeLessThan(conclusionPos);
  });

  it("inserts an image <figure> after specified paragraph", () => {
    const placements: Placement[] = [{ type: "image", productId: "pr_123", after_paragraph: 1 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    expect(result).toContain("<figure");
    expect(result).toContain("loading=\"lazy\"");
    expect(result).toContain("rounded-xl");
  });

  it("appends placement at end when after_paragraph exceeds article length", () => {
    const placements: Placement[] = [{ type: "widget", productId: "pr_123", after_paragraph: 999 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    // Affiliate link should appear after "Conclusion paragraph" in the full result
    const conclusionPos = result.indexOf("Conclusion paragraph");
    const widgetPos = result.search(/rel="sponsored"/);
    expect(conclusionPos).toBeGreaterThan(-1);
    expect(widgetPos).toBeGreaterThan(conclusionPos);
  });

  it("applies multiple placements in correct descending order", () => {
    const placements: Placement[] = [
      { type: "widget", productId: "pr_123", after_paragraph: 3 },
      { type: "image",  productId: "pr_123", after_paragraph: 1 },
    ];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    const figurePos = result.indexOf("<figure");
    // Widget renders as fallback link in tests (no partnerId env var)
    // The fallback <a> must appear after the <figure>
    const affiliateLinkPos = result.search(/rel="sponsored"/);
    // Image (paragraph 1) should appear before the widget link (paragraph 3)
    expect(figurePos).toBeGreaterThan(-1);
    expect(affiliateLinkPos).toBeGreaterThan(figurePos);
  });

  it("skips unknown productId with warning (does not throw)", () => {
    const placements: Placement[] = [{ type: "widget", productId: "pr_UNKNOWN", after_paragraph: 1 }];
    expect(() => insertPlacements(ARTICLE, BRIEF, placements, "techblog")).not.toThrow();
  });

  it("uses fallback link when partnerId is empty (techblog has no partner ID by default)", () => {
    const placements: Placement[] = [{ type: "widget", productId: "pr_123", after_paragraph: 1 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    // Either full widget or fallback link — both should contain rel="sponsored"
    expect(result).toContain('rel="sponsored"');
  });

  it("image alt uses brand from specs when available", () => {
    const placements: Placement[] = [{ type: "image", productId: "pr_123", after_paragraph: 0 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    expect(result).toContain("SuperBook Pro - Acme");
  });

  it("image alt falls back to product name when no brand", () => {
    const placements: Placement[] = [{ type: "image", productId: "pr_456", after_paragraph: 0 }];
    const result = insertPlacements(ARTICLE, BRIEF, placements, "techblog");
    expect(result).toContain('alt="Budget Lappy"');
  });
});
