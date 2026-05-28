## 1. Dependencies & Types

- [x] 1.1 Install `@modelcontextprotocol/sdk` (MCP server + Streamable HTTP transport)
- [x] 1.2 Install `marked` (Markdown → HTML conversion)
- [x] 1.3 Add `PlacementSchema` to `src/types/index.ts` — `{ type: "image"|"widget", productId: string, after_paragraph: number }`
- [x] 1.4 Add `SeoPayloadSchema` to `src/types/index.ts` — `{ title?, description?, slug?, focus_keyword?, featured_image_product_id? }`
- [x] 1.5 Update `PublishRequestSchema` — add `placements`, `seo`, `status` fields; replace article-only body
- [x] 1.6 Update `PublishResultSchema` — `{ status, wp_post_id, url, site, warnings[] }`
- [x] 1.7 Update `SiteConfig` interface — add `pricerunnerCountry`, `pricerunnerCategories`, `pricerunnerPartnerId`, `categoryMap`

## 2. Site Config

- [x] 2.1 Extend `src/config/sites.ts` — add `pricerunnerCountry`, `pricerunnerCategories`, `pricerunnerPartnerId`, `categoryMap` for all sites
- [x] 2.2 Add env var loading for WP credentials — `WP_{SITE_KEY_UPPER}_USER` and `WP_{SITE_KEY_UPPER}_APP_PASSWORD`

## 3. PriceRunner Client (v4 migration)

- [x] 3.1 Replace v3 endpoint with Category Browse v4: `/{country}/api/search-edge-rest/public/search/category/v4/{COUNTRY}/{id}?size=30&sorting=POPULARITY&device=desktop`
- [x] 3.2 Add keyword search endpoint: `/{country}/api/instant-search-edge-rest/public/search/suggest/{COUNTRY}?q={term}`
- [x] 3.3 Fix header strategy — clear all headers per request, set only `User-Agent` (rotated) + `Accept: application/json`
- [x] 3.4 Fix price parsing — `lowestPrice.amount` is a string; parse with `parseFloat()`; fallback to `cheapestOffer.price`
- [x] 3.5 Fix image URL — fallback `image.url` → `image.path`; prepend base URL if relative
- [x] 3.6 Add 1000ms minimum interval between requests (rate limit enforced via timestamp check)
- [x] 3.7 Add 24-hour in-memory cache keyed by `pricerunner-category:{id}:{country}`
- [x] 3.8 Map additional v4 fields — `brand.name`, `rating.average`, `rating.count`, `ribbon.type`, `priceDrop.percent`
- [x] 3.9 Update `scripts/seed.ts` to use the updated v4 client

## 4. Content Registry

- [x] 4.1 Create `src/services/content-registry.ts` — read/check/update per-site product ID ledger
- [x] 4.2 Implement atomic write — write to `data/content-registry.tmp.json`, then `fs.renameSync` to live file
- [x] 4.3 Implement `isProductUsed(siteKey, productId)` and `registerProducts(siteKey, productIds[])` exports
- [x] 4.4 Handle missing file on startup — treat as empty registry, create on first write

## 5. Category Traversal

- [x] 5.1 Create `src/services/category-traversal.ts` — traverse PR category hierarchy to leaf categories
- [x] 5.2 Implement leaf detection — category with no child entries in API response is a leaf; fetch products
- [x] 5.3 Implement `getMostUnwrittenLeafCategory(siteKey)` — traverse all configured categories, count fresh products per leaf, return richest
- [x] 5.4 Cache traversal results in memory with 24-hour TTL

## 6. Brief Generator Updates

- [x] 6.1 Integrate content registry check into `generateBrief` — filter out already-published product IDs for the given site
- [x] 6.2 Handle null/omitted category — call `getMostUnwrittenLeafCategory` to select leaf automatically
- [x] 6.3 Return structured error `{ error: "category_exhausted" }` when fewer than 3 fresh products remain
- [x] 6.4 Return structured error `{ error: "all_categories_exhausted" }` when no fresh leaf categories remain

## 7. Placement Engine (widget-inserter rewrite)

- [x] 7.1 Rewrite `src/services/widget-inserter.ts` — accept article string + placements array (remove placeholder logic)
- [x] 7.2 Implement paragraph splitter — split Markdown on `\n\n`
- [x] 7.3 Implement placement injection — sort descending by `after_paragraph`, insert HTML blocks; append at end if index exceeds paragraph count
- [x] 7.4 Implement image HTML block — `<figure>` with `loading="lazy"`, `border-radius: 8px`, correct alt text fallback chain
- [x] 7.5 Implement widget HTML block — full PriceRunner widget template (dynamic country, UUID per instance, `rel="sponsored"`, partnerId from site config)
- [x] 7.6 Implement widget fallback — plain `<a rel="sponsored" class="btn-primary">` when partnerId missing

## 8. Markdown → HTML

- [x] 8.1 Add `marked` conversion step after placement injection — convert full joined document to HTML before passing to publisher
- [x] 8.2 Extract H1 from converted HTML for SEO title/slug fallback

## 9. Inline Affiliate Link Conversion

- [x] 9.1 Create `src/services/affiliate-linker.ts` — scan HTML for product name mentions post-conversion
- [x] 9.2 Implement word-boundary, case-insensitive matching per product name
- [x] 9.3 Enforce max 2 links per product; skip mentions inside `<h1>`–`<h6>` tags
- [x] 9.4 Collect unmentioned products (0 matches) and return as `warnings[]`

## 10. WordPress Publisher

- [x] 10.1 Create `src/services/wp-publisher.ts` with same function signature as `file-writer.ts`
- [x] 10.2 Implement WP REST API POST to `/wp-json/wp/v2/posts` using axios + Basic auth (credentials from env vars)
- [x] 10.3 Implement RankMath meta fields — `rank_math_title`, `rank_math_description`, `rank_math_focus_keyword` from SEO payload
- [x] 10.4 Implement slug generation — use `seo.slug` if provided; else slugify H1 with Danish transliteration (æ→ae, ø→oe, å→aa)
- [x] 10.5 Implement WP category resolution — look up brief category in site config `categoryMap`; fallback to site default `categoryId`
- [x] 10.6 Apply exponential backoff on 5xx responses (reuse pattern from `pricerunner-client.ts`); mark job `failed` after max retries
- [x] 10.7 Update content registry on successful `status: "publish"` (not on draft)

## 11. MCP Server

- [x] 11.1 Create `src/mcp/server.ts` — initialise MCP server with `@modelcontextprotocol/sdk`, Streamable HTTP transport on port 3001
- [x] 11.2 Implement `get_brief` tool — input schema, handler calling brief generator, content registry check, error responses for exhausted categories
- [x] 11.3 Implement `publish_article` tool — input schema, handler calling placement engine → linker → wp-publisher, return result + warnings
- [x] 11.4 Start MCP server in `src/server.ts` alongside Fastify on startup
- [x] 11.5 Log MCP server URL on startup: `🤖 MCP server  http://localhost:3001/mcp`

## 12. REST API Updates

- [x] 12.1 Update `src/routes/generate.ts` publish route — swap `file-writer` import for `wp-publisher`; update response schema to `PublishResultSchema`
- [x] 12.2 Add `GET /mcp-info` endpoint to Fastify returning `{ mcpPort: 3001, transport: "streamable-http", endpoint: "/mcp", tools: ["get_brief", "publish_article"] }`

## 13. Docker

- [x] 13.1 Create `Dockerfile` — Node 20 Alpine, expose ports 3000 and 3001, copy source, run build
- [x] 13.2 Create `docker-compose.yml` — service with both ports mapped, env var stubs for WP credentials per site
- [x] 13.3 Add `.env.example` documenting all required env vars (`WP_TECHBLOG_USER`, `WP_TECHBLOG_APP_PASSWORD`, etc.)
