# Publisher — WordPress Publishing Rules

## Overview
Articles are published to WordPress via REST API v2 (wp-publisher.ts).
The full pipeline is: Markdown → placement injection → Markdown-to-HTML → affiliate link
insertion → WordPress POST with RankMath SEO meta.

## Requirements

### REQ-PUB-001 — WordPress Endpoint
The publisher SHALL POST to `{wp_base_url}/wp-json/wp/v2/posts` using HTTP Basic auth
(credentials from WP_{SITE_KEY_UPPER}_USER and WP_{SITE_KEY_UPPER}_APP_PASSWORD env vars).

### REQ-PUB-002 — Article Pipeline
The publisher SHALL apply the following steps in order:
1. `insertPlacements` — inject widget and image HTML at agent-specified paragraph positions
2. `marked` — convert the Markdown+HTML document to full HTML
3. `affiliateLinker` — scan HTML for product name mentions, insert sponsored links (max 2 per product)
4. POST to WordPress with title, content, status, slug, categories, and RankMath meta fields

### REQ-PUB-003 — SEO Metadata
When an `seo` object is provided, the publisher SHALL set:
- `rank_math_title`, `rank_math_description`, `rank_math_focus_keyword` as post meta
- `slug`: use `seo.slug` if provided; else slugify the H1 with Danish transliteration (æ→ae, ø→oe, å→aa)

### REQ-PUB-004 — Category Resolution
The publisher SHALL look up the brief category in the site config `categoryMap`.
If not found, it falls back to the site's default WordPress category ID.

### REQ-PUB-005 — Retry on Server Errors
The publisher SHALL apply exponential backoff on 5xx responses (same pattern as pricerunner-client.ts).
After max retries the job is marked `failed`.

### REQ-PUB-006 — Content Registry Update
On a successful publish with status="publish", the publisher SHALL register all brief product IDs
in the content registry for the given site. Draft publishes do NOT update the registry.

### REQ-PUB-007 — Response Shape
The publisher SHALL return: { status, wp_post_id, url, site, warnings[] }
`warnings` lists product names from the brief that had 0 text mentions in the final HTML.

## Scenarios

### Scenario: Successful publish
GIVEN a valid article, placements, seo payload, and status="publish"
WHEN the publisher runs the full pipeline
THEN the post is created in WordPress and { status: "published", wp_post_id, url, site } is returned
AND product IDs are written to the content registry

### Scenario: Draft publish
GIVEN status="draft"
WHEN the publisher posts to WordPress
THEN a draft post is created and { status: "draft", wp_post_id, url, site } is returned
AND the content registry is NOT updated

### Scenario: Product not mentioned
GIVEN a product from the brief has 0 text matches in the final HTML
WHEN the affiliate linker runs
THEN publish still succeeds but warnings contains the product name

### Scenario: WordPress server error
GIVEN the WP REST API returns 5xx
WHEN the publisher retries with backoff and all retries fail
THEN the job status is set to "failed" and an error is returned
