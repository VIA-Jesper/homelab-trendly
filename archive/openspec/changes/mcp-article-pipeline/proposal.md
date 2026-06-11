## Why

The current system exposes a REST API that generates a content brief but stops there - no agent
integration, no real publishing, and no structured way for an AI agent to complete the article
pipeline. The primary interface should be MCP tools, enabling an AI agent to get a brief, write
an article, and hand the finished package back to the system for publishing to WordPress.

## What Changes

- **NEW** MCP tool `get_brief` - agent entry point; `category` is optional. If provided,
  system looks up products in that category. If null, system decides what needs writing next
  based on content gaps. Either way, a content registry check runs before returning -
  products already used in a published article on that site are filtered out. If a category
  is exhausted (fewer than 3 fresh products remain), the tool returns an error so the agent
  can try a different category or pass null to let the system choose.
- **NEW** Content registry - per-site ledger tracking which product IDs have appeared in
  published articles. Prevents duplicate content. Phase 1: JSON file on disk.
  Phase 2: cross-referenced against WordPress existing posts.
- **NEW** MCP tool `publish_article` - agent submits finished article with SEO metadata,
  image/widget placements, and publish settings; system publishes to WordPress
- **NEW** WordPress publisher - replaces Phase 1 file-writer with live WP REST API publishing
- **NEW** SEO integration - RankMath field mapping (meta title, description, slug,
  focus keyword, featured image) applied on publish
- **CHANGED** Placement system - inline `{{PLACEHOLDER}}` markers replaced with a structured
  placement array `[{ type, productId, after_paragraph }]`. Markers were rejected due to
  real-world unreliability (agents produce malformed marker names causing broken published output)
- **NEW** Inline affiliate link conversion - system post-processing step (independent of agent
  placement). After widget/image injection and Markdown→HTML conversion, product name mentions
  in article text are auto-converted to `rel="sponsored"` affiliate links. Max 2 per product,
  never inside headings. Products with 0 mentions surfaced as warnings in publish response.
- **CHANGED** PriceRunner client - migrated from undocumented v3 internal endpoint to correct
  public Category Browse v4 API. Gains brand, rating, ribbon (trending), priceDrop fields.
  Header strategy corrected: clear all headers per request, set only User-Agent + Accept.
- **CHANGED** Site config - extended with `pricerunnerPartnerId` (affiliate ID, URL-encoded in
  widgets), `pricerunnerCategories` (list of PR category IDs at any hierarchy level - system
  traverses `/t/` nodes down to `/cl/` leaf categories automatically), a leaf-name → WP category
  ID map, and RankMath field mappings. Agent never handles PriceRunner or WP internals.
- **CHANGED** Widget generation - system generates the full PriceRunner widget HTML from a known
  template using productId, partnerId (site config), and a generated UUID per instance. Widget
  includes the Danish affiliate disclosure ("Annonce i samarbejde med PriceRunner") - self-disclosing.
- **CHANGED** Publish response - from `{ status, filePath }` to `{ status, wp_post_id, url, site }`
- **NEW** Markdown-to-HTML conversion - agent writes in Markdown, system converts server-side
  before sending to WordPress REST API. Keeps agent output clean; no WP plugin dependency.
- **CHANGED** MCP transport - HTTP/SSE (MCP server runs in Docker, exposes a port).
  stdio is not used; the server is a long-running process accessible over the network.
- REST API endpoints remain for developer/testing use; MCP is the production interface

## Deferred / Future
- **Images** - PriceRunner image URLs are hotlinked in Phase 1. Known risk (URL instability,
  potential ToS). Phase 2: download and upload to WordPress media library before publishing.
- **Null category algorithm** - Phase 1: pick category with most unwritten products remaining.
  Phase 2: replace with PriceRunner "recommended/trending products" feed filtered by site categories.
- **Multi-agent pipeline** - current design supports one agent doing all steps. Future: specialized
  agents each call their MCP tool sequentially; job store acts as shared session state.

## Capabilities

### New Capabilities
- `mcp-interface`: Two MCP tools (get_brief, publish_article) that form the primary agent interface
- `seo-integration`: RankMath SEO field generation, mapping, and WordPress REST API delivery

### Modified Capabilities
- `publisher`: File-writer replaced by WordPress REST API publisher; response format changes
- `widgets`: Placeholder-based insertion replaced by structured placement array engine
- `api`: Publish endpoint response updated to match new publisher response shape
- `brief`: get_brief MCP tool wraps brief generation; category is optional; content registry
  check runs before every brief; job_id returned alongside brief

## Impact

- `src/services/file-writer.ts` - replaced by `src/services/wp-publisher.ts`
- `src/services/widget-inserter.ts` - updated to use placement array instead of string replacement
- `src/routes/generate.ts` - publish response type updated
- `src/config/sites.ts` - extended with partnerId, pricerunnerCategories, categoryMap, RankMath fields
- `src/services/category-traversal.ts` - new; traverses PR hierarchy, caches leaf categories per site
- `src/scraper/pricerunner-client.ts` - migrated to Category Browse v4 + Keyword Search endpoints;
  corrected header strategy; price/image field parsing updated; brand/rating/ribbon fields added
- `src/types/index.ts` - new schemas: PlacementSchema, SeoPayloadSchema, PublishRequestSchema updated
- `src/mcp/` - new directory with MCP server and tool definitions
- `openspec/specs/publisher/spec.md` - delta spec: WP publishing requirements
- `openspec/specs/widgets/spec.md` - delta spec: structured placement requirements
- `src/services/content-registry.ts` - new; per-site ledger of used product IDs
- `data/content-registry.json` - new; Phase 1 persistence for content registry
- No other database changes; job store remains in-memory (Phase 1 boundary unchanged)
- New dependency: WordPress REST API client; RankMath plugin assumed on target sites
