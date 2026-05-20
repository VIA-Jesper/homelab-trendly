import { describe, it, expect } from "vitest";
import { slugify, resolveWpCategory } from "../../src/services/wp-publisher.js";

describe("slugify", () => {
  it("lowercases and replaces spaces with hyphens", () => {
    expect(slugify("Best Laptops 2025")).toBe("best-laptops-2025");
  });

  it("removes special characters", () => {
    expect(slugify("Top 5! Products (Review)")).toBe("top-5-products-review");
  });

  it("collapses multiple hyphens", () => {
    expect(slugify("Hello---World")).toBe("hello-world");
  });

  it("trims leading and trailing whitespace", () => {
    expect(slugify("  padded title  ")).toBe("padded-title");
  });

  describe("Danish transliteration", () => {
    it("converts æ → ae", () => {
      expect(slugify("Bedste Hørtelæpper")).toContain("ae");
      expect(slugify("Skæg")).toBe("skaeg");
    });

    it("converts ø → oe", () => {
      expect(slugify("Hørsel")).toBe("hoersel");
      expect(slugify("Høretelefoner")).toBe("hoeretelefoner");
    });

    it("converts å → aa", () => {
      expect(slugify("Årets Bedste")).toBe("aarets-bedste");
    });

    it("handles mixed Danish and normal chars", () => {
      expect(slugify("Bedste Høretelefoner")).toBe("bedste-hoeretelefoner");
    });

    it("full realistic slug", () => {
      expect(slugify("Bedste Høretelefoner 2025")).toBe("bedste-hoeretelefoner-2025");
    });
  });
});

describe("resolveWpCategory", () => {
  it("returns mapped WP category ID when category matches categoryMap", () => {
    // techblog site config has laptops → 5
    const categoryId = resolveWpCategory("techblog", "laptops");
    expect(categoryId).toBe(5);
  });

  it("is case-insensitive for category lookup", () => {
    const categoryId = resolveWpCategory("techblog", "Laptops");
    expect(categoryId).toBe(5);
  });

  it("falls back to site default categoryId when category not in map", () => {
    // "gaming" is not in techblog categoryMap; default is 5
    const categoryId = resolveWpCategory("techblog", "gaming");
    expect(categoryId).toBe(5);
  });

  it("resolves headphones category for budgetshop", () => {
    // budgetshop: headphones → 4
    const categoryId = resolveWpCategory("budgetshop", "headphones");
    expect(categoryId).toBe(4);
  });

  it("throws for completely unknown site key", () => {
    expect(() => resolveWpCategory("nonexistent-site", "laptops")).toThrow();
  });
});
