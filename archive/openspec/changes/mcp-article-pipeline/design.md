## Context

The current system is a Fastify REST API that generates content briefs from PriceRunner product
data and writes finished articles to disk. It has no agent integration, no WordPress publishing,
and no structured way for an AI agent to complete the pipeline end-to-end.

This design introduces a native MCP server running alongside the existing Fastify API in the same
Docker container. Two MCP tools form the agent interface: `get_brief` and `publish_article`.
The REST API remains untouched as a developer/testing surface.

## Goals / Non-Goals

**Goals:**
- Native MCP server with Streamable HTTP transport, Docker-deployable
- `get_brief` tool with optional category, content registry deduplication, and null-category selection
- `publish_article` tool accepting Markdown article, SEO fields, structured placements, publish settings
- WordPress REST API v2 publishing with RankMath SEO meta fields
- Markdown → HTML conversion server-side before WP publish
- Structured placement engine: inject images/widgets after specified paragraph indices
- Content registry: per-site JSON ledger preventing duplicate product sets in published articles
- Extended site config: WP credentials (env vars), PriceRunner tracking ID, category → WP ID map

**Non-Goals:**
- WordPress media library upload (images hotlinked in Phase 1)
- Multi-agent pipeline (single agent does all steps in Phase 1)
- System-level compliance validation (agent's responsibility)
- PriceRunner trending feed for null-category selection (Phase 2)
- Authentication on MCP endpoint (assumed private/internal network in Docker)

## Decisions

### 1. MCP Framework: `@modelcontextprotocol/sdk` (native, not OpenAPI wrapper)
The existing `server.ts` references `@ivotoby/openapi-mcp-server` which auto-generates MCP tools
from the OpenAPI spec. Rejected: tool descriptions are critical for correct agent behavior and
the wrapper gives no control over them. Error shapes, input schemas, and descriptions must be
hand-crafted for a reliable agent experience.
**Chosen:** `@modelcontextprotocol/sdk` with full control over tool definitions.

### 2. MCP Transport: Streamable HTTP on a dedicated port
MCP runs as a standalone HTTP server on port 3001, same Node.js process as Fastify (port 3000).
Single Docker container exposes both ports. Streamable HTTP (POST /mcp) is the current MCP spec
recommendation - Docker-friendly, no persistent connections required, works with all major agent
frameworks. Legacy SSE transport not used.
```
Docker container
├── Fastify   :3000  - REST API (dev/testing)
└── MCP Server :3001  - Agent interface (production)
    POST /mcp         - Streamable HTTP transport
```

### 3. Content Registry: atomic JSON writes, publish-only
Structure: `{ [siteKey: string]: string[] }` - flat array of product IDs per site.
Written only when `status: "publish"` (drafts do not lock products).
Atomic write pattern: write to `data/content-registry.tmp.json` → rename → replaces live file.
Prevents corruption on crash mid-write. Single Node.js process; event loop serializes naturally.
Phase 2: replace with DB query or WP posts cross-reference.

### 4. Null-category selection algorithm
When `category` is null in `get_brief`:
1. Load site's `pricerunnerCategories` list from site config
2. Traverse the PR category hierarchy (cached): recurse `/t/` nodes until `/cl/` leaf categories reached
3. For each leaf category, count products NOT already in the site's content registry
4. Select the leaf category with the highest fresh product count
5. Ties broken alphabetically (deterministic, predictable)
6. Build brief from that category's products
If all leaf categories are exhausted → return structured error: `{ error: "all_categories_exhausted" }`
Phase 2: replace step 4 with PriceRunner "recommended/trending" feed filtered to site categories.

### 5. Placement engine: agent-directed paragraph injection
The agent specifies exactly where each image and widget goes via the placements array.
The system places them precisely at the requested position - no auto-detection, no inference.

```
placements: [
  { type: "image",  productId: "pr_123", after_paragraph: 2 },
  { type: "widget", productId: "pr_123", after_paragraph: 3 },
  { type: "widget", productId: "pr_456", after_paragraph: 7 }
]
```

Pipeline:
1. Split Markdown article on `\n\n` into paragraph array
2. Collect all placements sorted by `after_paragraph` descending
3. For each placement, insert the appropriate HTML block after paragraph[N]
4. Graceful degradation: if `after_paragraph` exceeds paragraph count, append at end
5. Join paragraphs back and convert full document to HTML via `marked`

Applying in descending order preserves earlier paragraph indices.

Two HTML block types:
- **Image** (`type: "image"`) - `<figure>` with product image, `loading="lazy"`, `border-radius: 8px`
  Alt text: `{productName} - {brand}` if brand available, else `{productName}`
- **Widget** (`type: "widget"`) - full PriceRunner widget HTML (see Decision 11)

**Post-processing pass - inline affiliate link conversion:**
After widget/image placement and Markdown→HTML conversion, the system scans the article HTML
for product name mentions and converts them to affiliate links. This is independent of placement
- the agent does not control it, the system handles it automatically.

Rules (from reference, validated against PriceRunner affiliate terms):
- Match product names using word-boundary, case-insensitive search
- Convert up to **2 mentions per product** to avoid looking spammy (hurts SEO)
- **Never link mentions inside headings** (`<h1>`-`<h6>`)
- Link format: `<a href="{absoluteAffiliateUrl}?partnerId={urlEncodedPartnerId}" rel="sponsored">{mentionText}</a>`
- If a product has 0 mentions in the article, note it in the publish response as a warning
  (agent may have omitted a product from the brief - useful signal for the caller)

### 6. Markdown → HTML: `marked` library
`marked` is the standard Node.js Markdown→HTML converter - fast, dependency-light, no config needed.
Alternative `remark` (plugin-based, heavier) is overkill for structured article conversion.
Conversion happens after placement injection is complete (placements reference paragraph indices
in the Markdown source, not the HTML output).

### 7. WordPress auth: Application Passwords via environment variables
WP Application Passwords (built into WP 5.6+) sent as Basic auth header.
Credentials loaded from env vars at startup: `WP_{SITE_KEY}_USER`, `WP_{SITE_KEY}_APP_PASSWORD`
(e.g. `WP_TECHBLOG_USER`, `WP_TECHBLOG_APP_PASSWORD`). Site config reads env vars; no secrets
in code or config files.

### 8. RankMath SEO fields
Delivered via WP REST API `meta` field on post creation. Known RankMath meta keys:
`rank_math_title`, `rank_math_description`, `rank_math_focus_keyword`.
Featured image (`featured_media`) requires a WP media library ID - skipped in Phase 1 since
images are not uploaded. If RankMath is not installed, meta fields are silently ignored by WP;
publish succeeds, SEO meta is absent. System logs a warning but does not fail the request.

### 9. Site config: PriceRunner categories, country, and WP category map
Each site declares which PriceRunner category IDs it covers at any hierarchy level.
The system traverses `/t/` nodes down to `/cl/` leaf categories automatically using the
Category Browse v4 API. Leaf detection: category with no child entries = leaf, fetch products.

```ts
pricerunnerCountry: "DK"                       // DK | SE | NO | UK
pricerunnerCategories: ["34", "1448", "243"]   // mix of levels - system resolves
pricerunnerPartnerId: "adrunner_dk_techblog"   // plain string; system URL-encodes as needed
categoryMap: { "Køkkenknive": 12, "Bærbare computere": 5 }  // leaf name → WP category ID
```

Traversal applies 1000ms minimum rate limit between requests + UA rotation + backoff.
Results cached in memory with 24-hour TTL keyed by `pricerunner-category:{id}:{country}`.

### 10. PriceRunner API endpoints (corrected from existing codebase)
The existing `pricerunner-client.ts` uses an undocumented v3 internal endpoint - replaced:

```
Category Browse v4 (primary):
GET {baseUrl}/{country}/api/search-edge-rest/public/search/category/v4/{COUNTRY}/{categoryId}
    ?size=30&sorting=POPULARITY&device=desktop

Keyword Search (for category ID discovery):
GET {baseUrl}/{country}/api/instant-search-edge-rest/public/search/suggest/{COUNTRY}?q={term}
```

Base URLs: DK → `https://www.pricerunner.dk`, SE → `.se`, NO → `.no`, UK → `.co.uk`

Header strategy (per reference): clear all headers before each request, set ONLY:
- `User-Agent: {rotated browser UA}`
- `Accept: application/json`
Persistent Referer/Accept-Language headers are bot signals - removed from axios instance config.

`lowestPrice.amount` is returned as a **string** - parse with `parseFloat()`.
Price fallback: `lowestPrice` first, then `cheapestOffer.price`.
Image fallback: `image.url` first, then `image.path`. Relative URLs (`/pl/...`) → prepend base URL.

Additional fields available from v4 (enrich brief quality):
- `brand.name` - brand for alt text generation
- `rating.average`, `rating.count` - prioritise well-rated products in brief
- `ribbon.type` - `TRENDING_CATEGORY`, `PRICE_DROP_ABSOLUTE` signals boost product priority
- `priceDrop.percent` - mention in brief for agent to highlight

### 11. PriceRunner widget HTML template (updated)
```html
\n\n
<div id="pr-product-widget-{uuid}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/{countryLower}/product.js
       ?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3
       &productId={numericProductId}
       &partnerId={urlEncodedPartnerId}
       &widgetId=pr-product-widget-{uuid}" async></script>
<div style="display: inline-block">
  <a href="{absoluteAffiliateUrl}" rel="sponsored">
    <p style="font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic;
              color: var(--grayscale100); text-decoration: underline;">
      Annonce i samarbejde med <span style="font-weight:bold">PriceRunner</span>
    </p>
  </a>
</div>
\n\n
```

Key fields: `countryLower` from site config, `uuid` = `crypto.randomUUID()` per instance,
`numericProductId` = strip `pr_` prefix, `urlEncodedPartnerId` = `encodeURIComponent(partnerId)`.
`rel="sponsored"` is correct (Google's current affiliate link standard). `rel="nofollow"` is old.

Fallback (missing productId or partnerId):
`<p><a href="{absoluteUrl}" rel="sponsored" class="btn-primary">Se pris på {name}</a></p>`

### 10. PriceRunner widget HTML template
Widget HTML is fully system-generated - the agent never writes widget markup. The agent only
specifies `{ type: "widget", productId, after_paragraph }` in the placements array.

```html
<div id="pr-product-widget-{uuid}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/product.js
       ?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=4
       &productId={numericProductId}
       &partnerId={urlEncodedPartnerId}
       &widgetId=pr-product-widget-{uuid}" async></script>
<div style="display: inline-block">
  <a href="{affiliateUrl}" rel="nofollow">
    <p style="font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic;
              color: var(--grayscale100); text-decoration: underline;">
      Annonce i samarbejde med <span style="font-weight:bold">PriceRunner</span>
    </p>
  </a>
</div>
```

Field resolution:
- `uuid` → `crypto.randomUUID()` per widget instance
- `numericProductId` → strip `pr_` prefix from brief product ID
- `urlEncodedPartnerId` → `encodeURIComponent(siteConfig.pricerunnerPartnerId)`
- `affiliateUrl` → product's `affiliateUrl` from brief

The disclosure text ("Annonce i samarbejde med PriceRunner") satisfies the Danish compliance
requirement. The widget is self-disclosing - no separate disclosure element needed per widget.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| PriceRunner image URLs break over time | Noted as Phase 2 (WP media upload). Hotlinking is a known trade-off. |
| WP REST API returns error mid-publish | Retry with exponential backoff (same pattern as pricerunner-client.ts). Job marked `failed` after max retries. |
| RankMath not installed on target site | SEO meta silently dropped by WP. Log warning. Document as deployment requirement. |
| Agent sends wrong paragraph index | Placement appended at end of article. Article still readable. Not a hard failure. |
| Content registry diverges from WP reality (e.g. post deleted) | Acceptable in Phase 1. Phase 2 cross-references live WP posts. |
| Markdown from agent contains raw HTML | `marked` passes raw HTML through unchanged. Could cause layout issues. Agent prompt should discourage mixing. |
| PriceRunner v3 endpoint silently breaks | Existing seed script uses v3 - must be updated to v4. v3 may stop working without notice. |
| Category traversal produces too many API calls | 1000ms rate limit + 24h cache mitigates. Warm cache on server start. |


## Migration Plan

1. Add env vars for WP credentials to Docker config before deploy
2. `data/content-registry.json` created empty on first run (correct starting state)
3. MCP server starts on port 3001 alongside existing Fastify - no breaking change to REST API
4. `file-writer.ts` kept in place during transition; `wp-publisher.ts` added alongside it
5. Route handler swaps import once WP publisher is verified (per existing REQ-PUB-005)
6. `pricerunner-client.ts` migrated from v3 to v4 endpoint - seed script updated in tandem
7. Rollback: revert route import and pricerunner-client.ts, MCP server can be stopped independently

## Open Questions

- None - all decisions resolved during exploration and reference document review.
