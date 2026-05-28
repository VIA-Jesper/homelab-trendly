# MCP Interface — Agent Tool Definitions

## ADDED Requirements

### Requirement: MCP server transport
The MCP server SHALL run as a Streamable HTTP server on port 3001 in the same Node.js process
as the Fastify API. It SHALL accept POST requests at `/mcp` and comply with the MCP specification
for Streamable HTTP transport.

#### Scenario: Server starts on correct port
- **WHEN** the application starts
- **THEN** MCP server is listening on port 3001 at POST /mcp

---

### Requirement: get_brief tool
The MCP server SHALL expose a tool named `get_brief` with the following input schema:
- `category` (string, optional) — PriceRunner leaf category name to write about
- `productUrl` (string, optional) — specific product URL to build brief around
- `site` (string, required) — site key identifying which site config to use

If `category` is omitted, the system SHALL select the leaf category with the most unwritten
products for the given site (most-unwritten-first algorithm).

Before building the brief, the system SHALL check the content registry for the given site and
filter out any products already used in a published article. If fewer than 3 fresh products
remain in the resolved category, the tool SHALL return an error rather than a brief.

The tool SHALL return: `job_id`, and the full content brief (brief_id, category, products,
images, writing_rules, compliance).

#### Scenario: Category provided, fresh products available
- **WHEN** agent calls get_brief with category="laptops" and site="techblog"
- **THEN** system returns a brief with up to 5 fresh products and a job_id

#### Scenario: Category omitted — system selects
- **WHEN** agent calls get_brief with no category and site="techblog"
- **THEN** system picks the leaf category with the most unwritten products and returns a brief

#### Scenario: Category exhausted
- **WHEN** agent calls get_brief with a category where fewer than 3 fresh products remain
- **THEN** tool returns error `{ error: "category_exhausted", category: "laptops" }`

#### Scenario: All categories exhausted
- **WHEN** agent calls get_brief with no category and all site categories are exhausted
- **THEN** tool returns error `{ error: "all_categories_exhausted" }`

---

### Requirement: validate_article tool
The MCP server SHALL expose a tool named `validate_article` with the following input schema:
- `job_id` (string, required) — references the brief returned by get_brief
- `article` (string, required) — article content in Markdown
- `placements` (array, required) — planned widget/image placements (same shape as publish_article)

The tool SHALL validate the article against the brief and planned placements without publishing.
It SHALL return: `{ passed: boolean, wordCount: number, issues: string[], scores: { seo, voice, cro } }`.

Validation checks (all against the brief's article type rules from config/article-types.json):
- Word count within type-specific min/max range
- Affiliate disclosure present in the first 300 characters
- No forbidden superlatives from brief.compliance.forbiddenSuperlatives
- Verdict section present (if required by article type)
- Pros/cons sections present (if required by article type)
- All brief products mentioned in the article text (by first 30 chars of name)
- All placements reference valid paragraph indices

Scores (0-100 each):
- `seo`: deducted for missing H2+ headings
- `voice`: deducted per AI-tell phrase found (from type rules), and for spelling inconsistency
- `cro`: deducted for missing affiliate link in last paragraph and insufficient placement density

#### Scenario: Article passes all checks
- **WHEN** agent calls validate_article with a well-formed article, disclosure, all products mentioned
- **THEN** tool returns `{ passed: true, wordCount: <n>, issues: [], scores: { seo: 100, voice: 100, cro: 100 } }`

#### Scenario: Article fails disclosure check
- **WHEN** article has no disclosure phrase in first 300 characters
- **THEN** issues contains "Missing affiliate disclosure in opening 300 characters"
- **AND** passed is false

#### Scenario: Word count out of range
- **WHEN** article has fewer words than the type minimum
- **THEN** issues contains a word count message referencing the type name and minimum
- **AND** passed is false

#### Scenario: Unknown job_id
- **WHEN** agent calls validate_article with a job_id not in the job store
- **THEN** tool returns error `{ error: "job_not_found", job_id }`

---

### Requirement: publish_article tool
The MCP server SHALL expose a tool named `publish_article` with the following input schema:
- `job_id` (string, required) — references the brief returned by get_brief
- `article` (string, required) — article content in Markdown
- `site` (string, required) — site key
- `status` (enum, required) — `"publish"` or `"draft"`
- `placements` (array, required) — `[{ type: "image"|"widget", productId, after_paragraph }]`
- `seo` (object, optional) — `{ title?, description?, slug?, focus_keyword?, featured_image_product_id? }`

The tool SHALL: convert Markdown to HTML, inject placements, run inline affiliate link
conversion, apply SEO metadata, publish to WordPress, update the content registry (if status
is "publish"), and return the publish result.

The tool SHALL return: `{ status, wp_post_id, url, site, warnings[] }`.
`warnings` contains product names from the brief that had 0 mentions in the article.

#### Scenario: Successful publish
- **WHEN** agent calls publish_article with valid job_id, article, placements, and status="publish"
- **THEN** system publishes to WordPress and returns `{ status: "published", wp_post_id, url, site }`
- **AND** product IDs from the brief are written to the content registry for that site

#### Scenario: Published as draft
- **WHEN** agent calls publish_article with status="draft"
- **THEN** system creates a WordPress draft and returns `{ status: "draft", wp_post_id, url, site }`
- **AND** content registry is NOT updated (draft does not lock products)

#### Scenario: Unknown job_id
- **WHEN** agent calls publish_article with a job_id not in the job store
- **THEN** tool returns error `{ error: "job_not_found", job_id }`

#### Scenario: Product not mentioned in article
- **WHEN** a product from the brief has 0 text mentions in the final HTML
- **THEN** publish still succeeds but response includes `warnings: ["Product Name"]`
