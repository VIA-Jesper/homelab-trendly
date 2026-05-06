import axios, { type AxiosInstance } from "axios";
import type { RawProduct } from "../services/product-store.js";

// ─── User-Agent rotation ─────────────────────────────────────────────────────
const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
  "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
];

function randomUA(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)]!;
}

// ─── Exponential backoff ─────────────────────────────────────────────────────
async function withBackoff<T>(fn: () => Promise<T>, maxRetries = 4): Promise<T> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const retryable = status === 429 || status === 503 || (status !== undefined && status >= 500);
      if (!retryable || attempt === maxRetries) throw err;
      const delayMs = Math.min(1000 * 2 ** attempt + Math.random() * 500, 30_000);
      console.warn(`[pricerunner] HTTP ${status} — retry ${attempt + 1}/${maxRetries} in ${Math.round(delayMs)}ms`);
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw new Error("unreachable");
}

// ─── PriceRunner API client ───────────────────────────────────────────────────
const PR_BASE = "https://www.pricerunner.dk";

// Maps PriceRunner category slug → our internal category name
export const CATEGORY_MAP: Record<string, string> = {
  "baerbare-computere-17": "laptops",
  "hoeretelefoner-2451": "headphones",
  "mobiltelefoner-1": "phones",
  "tv-1344": "tvs",
};

function buildClient(): AxiosInstance {
  return axios.create({
    baseURL: PR_BASE,
    timeout: 15_000,
    headers: {
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "da-DK,da;q=0.9",
      "Referer": "https://www.pricerunner.dk/",
    },
  });
}

interface PriceRunnerProduct {
  id: string;
  name: string;
  lowestPrice: { amount: number; currency: string };
  topOffers: Array<{ merchant: { name: string }; price: { amount: number } }>;
  imageUrl: string;
  url: string;
  attributes?: Record<string, string>;
}

export async function fetchProductsByCategory(
  categorySlug: string,
  limit = 10
): Promise<RawProduct[]> {
  const client = buildClient();
  const internalCategory = CATEGORY_MAP[categorySlug] ?? categorySlug;

  const data = await withBackoff(async () => {
    const res = await client.get<{ products: PriceRunnerProduct[] }>(
      `/public/v3/dk/search/categories/${categorySlug}/pl`,
      {
        params: { limit, sortByPreset: "POPULAR" },
        headers: { "User-Agent": randomUA() },
      }
    );
    return res.data;
  });

  return data.products.map((p): RawProduct => ({
    id: `pr_${p.id}`,
    name: p.name,
    category: internalCategory,
    priceKr: p.lowestPrice.amount,
    retailer: p.topOffers[0]?.merchant.name ?? "PriceRunner",
    affiliateUrl: `${PR_BASE}${p.url}`,
    imageUrl: p.imageUrl,
    specs: p.attributes ?? {},
  }));
}
