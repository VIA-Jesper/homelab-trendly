import { describe, it, expect } from "vitest";
import { mapV4Product, computePopularityScore } from "../../src/scraper/pricerunner-client.js";
import type { V4Product } from "../../src/scraper/pricerunner-client.js";

const BASE = "https://www.pricerunner.dk";

function makeProduct(overrides: Partial<V4Product> = {}): V4Product {
  return {
    id: "3741515",
    name: "SuperBook Pro 15",
    lowestPrice: { amount: "8999.00", currency: "DKK" },
    image: { url: "https://cdn.pricerunner.dk/img/123.jpg" },
    url: "/pl/3741515-superbook",
    brand: { name: "Acme" },
    rating: { average: 4.5, count: 120 },
    ribbon: { type: "TRENDING_CATEGORY" },
    priceDrop: { percent: 15 },
    topOffers: [{ merchant: { name: "TechShop" } }],
    ...overrides,
  };
}

describe("mapV4Product - price parsing", () => {
  it("parses lowestPrice.amount from string to float", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.priceKr).toBe(8999.0);
    expect(typeof product.priceKr).toBe("number");
  });

  it("handles decimal string prices correctly", () => {
    const product = mapV4Product(makeProduct({ lowestPrice: { amount: "12499.50", currency: "DKK" } }), BASE, "laptops");
    expect(product.priceKr).toBe(12499.50);
  });

  it("falls back to cheapestOffer.price when lowestPrice is missing", () => {
    const p = makeProduct({ lowestPrice: undefined, cheapestOffer: { price: { amount: 5500 } } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.priceKr).toBe(5500);
  });

  it("returns 0 when both price sources are missing", () => {
    const p = makeProduct({ lowestPrice: undefined, cheapestOffer: undefined });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.priceKr).toBe(0);
  });
});

describe("mapV4Product - image URL", () => {
  it("uses image.url when present (absolute)", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.imageUrl).toBe("https://cdn.pricerunner.dk/img/123.jpg");
  });

  it("falls back to image.path when image.url is missing", () => {
    const p = makeProduct({ image: { path: "/img/fallback.jpg" } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.imageUrl).toBe(`${BASE}/img/fallback.jpg`);
  });

  it("makes relative image.url absolute", () => {
    const p = makeProduct({ image: { url: "/img/relative.jpg" } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.imageUrl).toBe(`${BASE}/img/relative.jpg`);
  });

  it("returns base URL as fallback when image is completely missing", () => {
    const p = makeProduct({ image: undefined });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.imageUrl).toBe(BASE);
  });
});

describe("mapV4Product - affiliate URL", () => {
  it("makes relative product URL absolute", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.affiliateUrl).toBe(`${BASE}/pl/3741515-superbook`);
  });

  it("leaves absolute URL unchanged", () => {
    const p = makeProduct({ url: "https://external.pricerunner.dk/pl/abc" });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.affiliateUrl).toBe("https://external.pricerunner.dk/pl/abc");
  });
});

describe("mapV4Product - additional fields", () => {
  it("maps brand.name to specs.brand", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.specs["brand"]).toBe("Acme");
  });

  it("maps rating to specs.rating string", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.specs["rating"]).toContain("4.5");
    expect(product.specs["rating"]).toContain("120");
  });

  it("maps ribbon.type to specs.ribbon", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.specs["ribbon"]).toBe("TRENDING_CATEGORY");
  });

  it("maps priceDrop.percent to specs.priceDrop", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.specs["priceDrop"]).toBe("15%");
  });

  it("prefixes product ID with pr_", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.id).toBe("pr_3741515");
  });

  it("uses topOffers merchant as retailer", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.retailer).toBe("TechShop");
  });

  it("falls back to PriceRunner when topOffers is empty", () => {
    const p = makeProduct({ topOffers: [] });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.retailer).toBe("PriceRunner");
  });

  it("prefers cheapestOffer merchant over topOffers", () => {
    const p = makeProduct({
      cheapestOffer: { price: { amount: 7999 }, merchant: { name: "CheapShop" } },
    });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.retailer).toBe("CheapShop");
  });
});

describe("mapV4Product - popularity signals", () => {
  it("maps rank.rank to specs.popularityRank", () => {
    const p = makeProduct({ rank: { rank: 3 } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.specs["popularityRank"]).toBe("3");
  });

  it("maps ribbon.value to specs.watchedLabel", () => {
    const p = makeProduct({ ribbon: { type: "WATCHED", value: "200+" } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.specs["watchedLabel"]).toBe("200+");
    expect(product.specs["ribbon"]).toBe("WATCHED");
  });

  it("maps previewMerchants.count to specs.merchantCount", () => {
    const p = makeProduct({ previewMerchants: { count: 21 } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.specs["merchantCount"]).toBe("21");
  });

  it("maps description to specs.description", () => {
    const p = makeProduct({ description: "En kraftig el-sav til professionelle" });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.specs["description"]).toBe("En kraftig el-sav til professionelle");
  });

  it("computes popularityScore > 0 for a watched + ranked product", () => {
    const p = makeProduct({ ribbon: { type: "WATCHED", value: "200+" }, rank: { rank: 1 } });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.popularityScore).toBeGreaterThan(0);
    expect(product.specs["popularityScore"]).toBeDefined();
  });

  it("defaults outOfStock to false", () => {
    const product = mapV4Product(makeProduct(), BASE, "laptops");
    expect(product.outOfStock).toBe(false);
  });

  it("captures outOfStock=true when API signals it", () => {
    const p = makeProduct({ outOfStock: true });
    const product = mapV4Product(p, BASE, "laptops");
    expect(product.outOfStock).toBe(true);
  });
});

describe("computePopularityScore", () => {
  it("gives 40pts for 200+ watchers", () => {
    const p = makeProduct({ ribbon: { type: "WATCHED", value: "200+" } });
    expect(computePopularityScore(p)).toBeGreaterThanOrEqual(40);
  });

  it("gives 30pts for 100+ watchers", () => {
    const p: V4Product = { id: "x", name: "X", ribbon: { type: "WATCHED", value: "100+" } };
    expect(computePopularityScore(p)).toBeGreaterThanOrEqual(30);
  });

  it("gives 30pts for rank 1", () => {
    const p: V4Product = { id: "x", name: "X", rank: { rank: 1 } };
    expect(computePopularityScore(p)).toBeGreaterThanOrEqual(30);
  });

  it("gives more points to rank 1 + 200 watchers than rank 5 alone", () => {
    const top = makeProduct({ ribbon: { type: "WATCHED", value: "200+" }, rank: { rank: 1 } });
    const mid = makeProduct({ rank: { rank: 5 } });
    expect(computePopularityScore(top)).toBeGreaterThan(computePopularityScore(mid));
  });

  it("returns 0 for a bare product with no signals", () => {
    const p: V4Product = { id: "x", name: "X" };
    expect(computePopularityScore(p)).toBe(0);
  });

  it("adds merchant depth bonus for >20 merchants", () => {
    const withMerchants: V4Product = { id: "x", name: "X", previewMerchants: { count: 25 } };
    const withoutMerchants: V4Product = { id: "x", name: "X" };
    expect(computePopularityScore(withMerchants)).toBeGreaterThan(computePopularityScore(withoutMerchants));
  });
});
