# PriceRunner Scraper — Reference Document

This document extracts everything needed to reuse or replicate the PriceRunner scraping logic from Trendly. No API key required — all endpoints are public-facing web APIs that the PriceRunner website itself calls.

---

## Overview

Trendly uses two distinct PriceRunner endpoints:

| Endpoint | Purpose | Used For |
|---|---|---|
| Instant Search / Suggest | Keyword → products + autocomplete suggestions | Finding products by search term |
| Category Browse v4 | Category ID → ranked product list | Browsing a specific category's products |

Both endpoints return JSON, require no authentication, and only need browser-like headers to avoid blocks.

---

## Endpoint 1 — Instant Search (Keyword Search)

### URL Pattern

```
GET https://www.pricerunner.{tld}/{country_lower}/api/instant-search-edge-rest/public/search/suggest/{COUNTRY_UPPER}?q={encoded_keyword}
```

**Examples:**
```
https://www.pricerunner.dk/dk/api/instant-search-edge-rest/public/search/suggest/DK?q=varmepumpe
https://www.pricerunner.se/se/api/instant-search-edge-rest/public/search/suggest/SE?q=v%C3%A4rmepump
https://www.pricerunner.co.uk/uk/api/instant-search-edge-rest/public/search/suggest/UK?q=heat+pump
```

### Country → Base URL Mapping

```
DK → https://www.pricerunner.dk
SE → https://www.pricerunner.se
NO → https://www.pricerunner.no
UK → https://www.pricerunner.co.uk
```

### Required Headers

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36
Accept: application/json
```

Rotate User-Agent across a few real browser strings to reduce block risk:
- `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36`
- `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0`
- `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15`

### Response Shape

```json
{
  "products": [
    {
      "id": "prod-123",
      "name": "Mitsubishi Ecodan 8kW",
      "url": "/pl/prod-123",
      "categoryName": "Varmepumper",
      "lowestPrice": {
        "amount": "15000",
        "currency": "DKK"
      },
      "image": {
        "id": "img-123",
        "url": "https://images.pricerunner.com/product/123.jpg",
        "path": "/images/product/123.jpg"
      }
    }
  ],
  "suggestions": [
    {
      "id": "345",
      "name": "Varmepumper",
      "type": "CATEGORY",
      "url": "/cl/345/Varmepumper"
    },
    {
      "id": "456",
      "name": "Bosch",
      "type": "BRAND",
      "url": "/brand/456/Bosch"
    },
    {
      "name": "varmepumpe luft til luft",
      "type": "QUERY"
    }
  ]
}
```

**Key notes:**
- `lowestPrice.amount` is a **string**, not a number — parse with `decimal.TryParse`
- `image.url` can be null; fall back to `image.path`
- `suggestions[].id` can be null (e.g., for `QUERY` type suggestions)
- Suggestion types: `CATEGORY`, `BRAND`, `PRODUCT`, `QUERY`
- Category suggestions include the category ID in the URL: `/cl/{id}/{slug}` — extract `id` from this

---

## Endpoint 2 — Category Browse (v4)

### URL Pattern

```
GET https://www.pricerunner.{tld}/{country_lower}/api/search-edge-rest/public/search/category/v4/{COUNTRY_UPPER}/{categoryId}?size={size}&sorting={sorting}&device=desktop
```

**Example:**
```
https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK/345?size=30&sorting=POPULARITY&device=desktop
```

### Parameters

| Parameter | Values | Notes |
|---|---|---|
| `size` | integer | Number of products (max observed: 30–50) |
| `sorting` | `POPULARITY`, `PRICE_ASC`, `PRICE_DESC`, `RATING` | Default: `POPULARITY` |
| `device` | `desktop` | Always `desktop` |

### Response Shape

```json
{
  "products": [
    {
      "id": "prod-123",
      "name": "Mitsubishi Ecodan 8kW",
      "url": "/pl/prod-123",
      "categoryName": "Varmepumper",
      "brand": {
        "name": "Mitsubishi"
      },
      "lowestPrice": {
        "amount": "15000",
        "currency": "DKK"
      },
      "cheapestOffer": {
        "price": {
          "amount": "14900",
          "currency": "DKK"
        }
      },
      "image": {
        "id": "img-123",
        "url": "https://images.pricerunner.com/product/123.jpg",
        "path": null
      },
      "ribbon": {
        "type": "TRENDING_CATEGORY",
        "value": null
      },
      "rating": {
        "average": 4.5,
        "count": 120
      },
      "priceDrop": {
        "percent": 12.5
      }
    }
  ],
  "categoryInfo": {
    "id": "345",
    "name": "Varmepumper",
    "path": [
      { "id": "1", "name": "Hjem & Have" },
      { "id": "345", "name": "Varmepumper" }
    ]
  }
}
```

**Key notes:**
- `ribbon.type` values observed: `TRENDING_CATEGORY`, `WATCHED`, `PRICE_DROP_ABSOLUTE`, `TOP_RATED_CATEGORY`
- `ribbon.value` may contain values like `"100+"` (watched count)
- `priceDrop.percent` is a double (e.g., `12.5` = 12.5% drop)
- Price fallback: use `lowestPrice` first, then `cheapestOffer.price`
- `categoryInfo.path` gives the full breadcrumb hierarchy

---

## Finding Category IDs

Category IDs appear in two ways:

1. **From search suggestions** — when you search a keyword, the `suggestions` array contains `CATEGORY` type entries with the category ID. URL format: `/cl/{categoryId}/{slug}`. The ID is the number after `/cl/`.

2. **Manually** — browse PriceRunner in a browser, navigate to a category page. The URL contains the category ID: `pricerunner.dk/cl/345/Varmepumper` → ID is `345`.

---

## Rate Limiting

- Trendly uses **1000ms minimum interval** between requests (configurable)
- Enforced with a `SemaphoreSlim(1,1)` + timestamp check
- No observed hard rate limit from PriceRunner, but aggressive scraping may trigger blocks

---

## Anti-Block Strategy

1. Rotate User-Agent on every request (pick randomly from a pool of real browser UAs)
2. Clear all headers before each request and set only `User-Agent` + `Accept`
3. Respect 1s rate limit between requests
4. Results are cached for 24 hours to avoid redundant requests

---

## Caching

Trendly wraps both endpoints in a cache using PostgreSQL (`ApiCache` table with key + JSON value + expiry). Cache keys follow the pattern:

```
pricerunner:{keyword}:{country}          // for keyword search
pricerunner-category:{categoryId}:{country}  // for category browse
```

Cache TTL: 24 hours. You can skip this for a standalone scraper and implement your own caching strategy.

---

## C# Implementation (Self-Contained)

Below is a minimal, dependency-free version of the scraper logic (no EF Core, no caching, no DI):

```csharp
using System.Text.Json;
using System.Text.Json.Serialization;

// ===== MODELS =====

public record SearchResult(List<ProductDto> Products, List<SuggestionDto> Suggestions);

public record ProductDto(
    string Id, string Name, string Url, string CategoryName,
    decimal? Price, string? Currency, string? ImageUrl);

public record SuggestionDto(string Name, string Type, string? Id, string? Url);

public record CategoryBrowseResult(List<CategoryProductDto> Products, string? CategoryName);

public record CategoryProductDto(
    string Id, string Name, string Url, string CategoryName,
    decimal? Price, string? Currency, string? ImageUrl,
    string? BrandName, string? RibbonType, double? RatingAverage, int? RatingCount, double? PriceDropPercent);

// ===== INTERNAL API MODELS =====

class ApiResponse { 
    [JsonPropertyName("products")] public List<ApiProduct> Products { get; set; } = new();
    [JsonPropertyName("suggestions")] public List<ApiSuggestion> Suggestions { get; set; } = new();
}
class ApiProduct {
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("categoryName")] public string CategoryName { get; set; } = "";
    [JsonPropertyName("lowestPrice")] public ApiPrice? LowestPrice { get; set; }
    [JsonPropertyName("image")] public ApiImage? Image { get; set; }
}
class ApiPrice {
    [JsonPropertyName("amount")] public string Amount { get; set; } = "0";
    [JsonPropertyName("currency")] public string Currency { get; set; } = "";
    public decimal Decimal => decimal.TryParse(Amount, out var v) ? v : 0;
}
class ApiImage {
    [JsonPropertyName("url")] public string? Url { get; set; }
    [JsonPropertyName("path")] public string? Path { get; set; }
}
class ApiSuggestion {
    [JsonPropertyName("id")] public string? Id { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("url")] public string? Url { get; set; }
}
class CategoryApiResponse {
    [JsonPropertyName("products")] public List<CategoryApiProduct> Products { get; set; } = new();
    [JsonPropertyName("categoryInfo")] public CategoryInfo? CategoryInfo { get; set; }
}
class CategoryApiProduct {
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("categoryName")] public string CategoryName { get; set; } = "";
    [JsonPropertyName("brand")] public ApiBrand? Brand { get; set; }
    [JsonPropertyName("lowestPrice")] public ApiPrice? LowestPrice { get; set; }
    [JsonPropertyName("cheapestOffer")] public ApiCheapestOffer? CheapestOffer { get; set; }
    [JsonPropertyName("image")] public ApiImage? Image { get; set; }
    [JsonPropertyName("ribbon")] public ApiRibbon? Ribbon { get; set; }
    [JsonPropertyName("rating")] public ApiRating? Rating { get; set; }
    [JsonPropertyName("priceDrop")] public ApiPriceDrop? PriceDrop { get; set; }
}
class ApiBrand { [JsonPropertyName("name")] public string Name { get; set; } = ""; }
class ApiCheapestOffer { [JsonPropertyName("price")] public ApiPrice? Price { get; set; } }
class ApiRibbon { [JsonPropertyName("type")] public string Type { get; set; } = ""; [JsonPropertyName("value")] public string? Value { get; set; } }
class ApiRating { [JsonPropertyName("average")] public double Average { get; set; } [JsonPropertyName("count")] public int Count { get; set; } }
class ApiPriceDrop { [JsonPropertyName("percent")] public double Percent { get; set; } }
class CategoryInfo { [JsonPropertyName("name")] public string Name { get; set; } = ""; }

// ===== SCRAPER =====

public class PriceRunnerScraper : IDisposable
{
    private readonly HttpClient _http = new();
    private readonly int _rateLimitMs;
    private DateTime _lastRequest = DateTime.MinValue;
    private readonly SemaphoreSlim _lock = new(1, 1);

    private static readonly string[] UserAgents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
    ];

    private static readonly JsonSerializerOptions JsonOpts = new() { PropertyNameCaseInsensitive = true };

    public PriceRunnerScraper(int rateLimitMs = 1000) => _rateLimitMs = rateLimitMs;

    public async Task<SearchResult?> SearchAsync(string keyword, string country = "DK", CancellationToken ct = default)
    {
        var baseUrl = GetBaseUrl(country);
        var url = $"{baseUrl}/{country.ToLower()}/api/instant-search-edge-rest/public/search/suggest/{country.ToUpper()}?q={Uri.EscapeDataString(keyword)}";
        var json = await FetchAsync(url, ct);
        if (json == null) return null;

        var resp = JsonSerializer.Deserialize<ApiResponse>(json, JsonOpts);
        if (resp == null) return null;

        var products = resp.Products.Select(p => new ProductDto(
            p.Id, p.Name, p.Url, p.CategoryName,
            p.LowestPrice?.Decimal, p.LowestPrice?.Currency,
            p.Image?.Url ?? p.Image?.Path)).ToList();

        var suggestions = resp.Suggestions.Select(s =>
            new SuggestionDto(s.Name, s.Type, s.Id, s.Url)).ToList();

        return new SearchResult(products, suggestions);
    }

    public async Task<CategoryBrowseResult?> BrowseCategoryAsync(string categoryId, string country = "DK", int size = 30, string sorting = "POPULARITY", CancellationToken ct = default)
    {
        var baseUrl = GetBaseUrl(country);
        var url = $"{baseUrl}/{country.ToLower()}/api/search-edge-rest/public/search/category/v4/{country.ToUpper()}/{categoryId}?size={size}&sorting={sorting}&device=desktop";
        var json = await FetchAsync(url, ct);
        if (json == null) return null;

        var resp = JsonSerializer.Deserialize<CategoryApiResponse>(json, JsonOpts);
        if (resp == null) return null;

        var products = resp.Products.Select(p => new CategoryProductDto(
            p.Id, p.Name, p.Url, p.CategoryName,
            p.LowestPrice?.Decimal ?? p.CheapestOffer?.Price?.Decimal,
            p.LowestPrice?.Currency ?? p.CheapestOffer?.Price?.Currency,
            p.Image?.Url ?? p.Image?.Path,
            p.Brand?.Name, p.Ribbon?.Type,
            p.Rating?.Average, p.Rating?.Count, p.PriceDrop?.Percent)).ToList();

        return new CategoryBrowseResult(products, resp.CategoryInfo?.Name);
    }

    private async Task<string?> FetchAsync(string url, CancellationToken ct)
    {
        await _lock.WaitAsync(ct);
        try
        {
            var elapsed = DateTime.UtcNow - _lastRequest;
            var minInterval = TimeSpan.FromMilliseconds(_rateLimitMs);
            if (elapsed < minInterval)
                await Task.Delay(minInterval - elapsed, ct);
            _lastRequest = DateTime.UtcNow;

            _http.DefaultRequestHeaders.Clear();
            _http.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", UserAgents[Random.Shared.Next(UserAgents.Length)]);
            _http.DefaultRequestHeaders.TryAddWithoutValidation("Accept", "application/json");

            var response = await _http.GetAsync(url, ct);
            if (!response.IsSuccessStatusCode) return null;
            return await response.Content.ReadAsStringAsync(ct);
        }
        catch { return null; }
        finally { _lock.Release(); }
    }

    private static string GetBaseUrl(string country) => country.ToUpper() switch
    {
        "SE" => "https://www.pricerunner.se",
        "NO" => "https://www.pricerunner.no",
        "UK" => "https://www.pricerunner.co.uk",
        _ => "https://www.pricerunner.dk"
    };

    public void Dispose() { _http.Dispose(); _lock.Dispose(); }
}
```

### Usage Example

```csharp
await using var scraper = new PriceRunnerScraper(rateLimitMs: 1000);

// Keyword search
var result = await scraper.SearchAsync("varmepumpe", "DK");
foreach (var product in result?.Products ?? [])
    Console.WriteLine($"{product.Name}: {product.Price} {product.Currency}");

// Category browse
var categoryResult = await scraper.BrowseCategoryAsync("345", "DK", size: 30);
foreach (var product in categoryResult?.Products ?? [])
    Console.WriteLine($"{product.Name} | Brand: {product.BrandName} | Rating: {product.RatingAverage}");

// Get category ID from search suggestions
var search = await scraper.SearchAsync("el-scooter", "DK");
var categorySuggestion = search?.Suggestions.FirstOrDefault(s => s.Type == "CATEGORY");
if (categorySuggestion?.Url != null)
{
    // URL format: /cl/345/Slug → extract "345"
    var id = categorySuggestion.Url.Split('/').Skip(2).FirstOrDefault();
    if (id != null)
    {
        var catResult = await scraper.BrowseCategoryAsync(id, "DK");
    }
}
```

---

## Known Product Fields

### From keyword search (`/suggest`)
| Field | Type | Notes |
|---|---|---|
| `id` | string | PriceRunner product ID |
| `name` | string | Product display name |
| `url` | string | Relative URL, e.g. `/pl/prod-123` |
| `categoryName` | string | Category label |
| `lowestPrice.amount` | string (parse as decimal) | Lowest price |
| `lowestPrice.currency` | string | e.g. `DKK`, `SEK` |
| `image.url` | string? | Absolute image URL |
| `image.path` | string? | Fallback image path |

### Additional fields from category browse (`/category/v4`)
| Field | Type | Notes |
|---|---|---|
| `brand.name` | string? | Brand name |
| `description` | string? | Short product description, often absent |
| `ribbon.type` | string? | `TRENDING_CATEGORY`, `WATCHED`, `PRICE_DROP_ABSOLUTE`, `TOP_RATED_CATEGORY` |
| `ribbon.value` | string? | Present when `type=WATCHED`: e.g. `"50+"`, `"100+"`, `"200+"` — price-watcher count tier |
| `rating.average` | double? | Star rating 0–5 |
| `rating.count` | int? | Number of ratings |
| `priceDrop.percent` | double? | Recent price drop % |
| `cheapestOffer.price` | price object | Alternative price source (use as fallback if `lowestPrice` absent) |
| `cheapestOffer.merchant.name` | string? | Merchant offering the cheapest price — use as display retailer |
| `rank.rank` | int? | PriceRunner's composite popularity position within the category (1 = most popular). Reflects clicks, comparisons, and purchase intent weighted together |
| `previewMerchants.count` | int? | Number of merchants currently stocking this product. High count = wide availability + commercial maturity |
| `outOfStock` | boolean? | True if no merchants have stock. Filter these out before selecting products for articles |
| `categoryInfo.name` | string | Category display name |
| `categoryInfo.path` | array | Breadcrumb path with id + name |

### Popularity signals — interpretation guide

The v4 category endpoint returns three independent demand signals. Understanding what each measures is important for using them correctly:

| Signal | What it measures | Strength |
|---|---|---|
| `ribbon.value` (e.g. `"200+"`) | **Purchase intent** — users with active price alerts. These people have decided on the product and are waiting to buy. The strongest signal of real demand. | High |
| `rank.rank` | **Discovery demand** — PriceRunner's composite score of clicks, comparisons, and views. Measures what people are researching, not necessarily buying. | Medium |
| `previewMerchants.count` | **Market validation** — how many retailers stock this product. High count means the market has decided it's worth carrying; also correlates with price competition and product longevity. | Supporting |

**Ribbon value tiers observed:** `"50+"`, `"100+"`, `"200+"`. A product at 200+ watchers in a niche category (e.g. power saws) is exceptional — it indicates very high purchase intent relative to category size.

**Brand dominance** is available indirectly via the `quickFilters` field in the response (not mapped in Trendly). It lists brands with product counts, e.g. Makita (224), Bosch (186), DeWalt (135). Useful for understanding which brands actually lead a category.

---

## Observed Limitations

- No pagination on keyword search — returns top ~10 products and ~10 suggestions
- Category browse supports `size` param (up to ~50 observed), no cursor/page support discovered yet
- Responses are cached by PriceRunner's CDN, so results may lag a few minutes behind live data
- No webhook or push mechanism — polling only
