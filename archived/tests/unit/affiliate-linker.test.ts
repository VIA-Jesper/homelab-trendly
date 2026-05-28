import { describe, it, expect } from "vitest";
import {
  convertMarkdownToHtml,
  extractH1,
  insertAffiliateLinks,
} from "../../src/services/affiliate-linker.js";
import type { ContentBrief } from "../../src/types/index.js";

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
      specs: {},
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
  images: [],
  writing_rules: { tone: "neutral", minWords: 600, maxWords: 1200, includeProsCons: true, includeVerdict: true },
  compliance: { requireDisclosure: true, disclosurePhrases: [], forbiddenSuperlatives: [] },
};

describe("convertMarkdownToHtml", () => {
  it("converts heading to <h1>", () => {
    const html = convertMarkdownToHtml("# Hello World");
    expect(html).toContain("<h1>Hello World</h1>");
  });

  it("converts bold text", () => {
    const html = convertMarkdownToHtml("**bold**");
    expect(html).toContain("<strong>bold</strong>");
  });

  it("preserves injected HTML blocks", () => {
    const md = "Intro\n\n<figure><img src=\"x.jpg\"></figure>\n\nConclusion";
    const html = convertMarkdownToHtml(md);
    expect(html).toContain("<figure>");
    expect(html).toContain("Intro");
  });
});

describe("extractH1", () => {
  it("extracts text from first <h1>", () => {
    const html = "<h1>Bedste Laptops 2025</h1><p>Content</p>";
    expect(extractH1(html)).toBe("Bedste Laptops 2025");
  });

  it("strips inner tags from h1", () => {
    const html = "<h1><strong>Bold Title</strong></h1>";
    expect(extractH1(html)).toBe("Bold Title");
  });

  it("returns undefined when no <h1> present", () => {
    const html = "<h2>Subheading</h2><p>Content</p>";
    expect(extractH1(html)).toBeUndefined();
  });
});

describe("insertAffiliateLinks", () => {
  it("converts first mention of product to affiliate link", () => {
    const html = "<p>The SuperBook Pro is a great laptop.</p>";
    const { html: result } = insertAffiliateLinks(html, BRIEF, "techblog");
    expect(result).toContain('<a href=');
    expect(result).toContain('rel="sponsored"');
    expect(result).toContain("SuperBook Pro");
  });

  it("converts up to 2 mentions, leaves third as plain text", () => {
    const html = "<p>SuperBook Pro here. SuperBook Pro there. SuperBook Pro everywhere.</p>";
    const { html: result } = insertAffiliateLinks(html, BRIEF, "techblog");
    const linkCount = (result.match(/<a /g) ?? []).length;
    expect(linkCount).toBe(2);
  });

  it("does NOT link product name inside heading tags", () => {
    const html = "<h2>SuperBook Pro Review</h2><p>The SuperBook Pro is fast.</p>";
    const { html: result } = insertAffiliateLinks(html, BRIEF, "techblog");
    // Only the body mention should be linked, not the heading
    expect(result).toContain("<h2>SuperBook Pro Review</h2>");
    const h2Portion = result.match(/<h2>.*?<\/h2>/s)?.[0] ?? "";
    expect(h2Portion).not.toContain('<a ');
  });

  it("adds product name to warnings when 0 mentions found", () => {
    const html = "<p>This article doesn't mention either product.</p>";
    const { warnings } = insertAffiliateLinks(html, BRIEF, "techblog");
    expect(warnings).toContain("SuperBook Pro");
    expect(warnings).toContain("Budget Lappy");
  });

  it("does not warn about products that are mentioned", () => {
    const html = "<p>The SuperBook Pro and Budget Lappy are both reviewed here.</p>";
    const { warnings } = insertAffiliateLinks(html, BRIEF, "techblog");
    expect(warnings).toHaveLength(0);
  });

  it("matching is case-insensitive", () => {
    const html = "<p>The superbook pro is fast.</p>";
    const { html: result } = insertAffiliateLinks(html, BRIEF, "techblog");
    expect(result).toContain('<a ');
  });
});
