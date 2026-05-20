# Widgets — Delta Spec

## REMOVED Requirements

### Requirement: Placeholder Format
**Reason:** Inline placeholder markers (`{{AFFILIATE_WIDGET_*}}`) rejected. Real-world agent
usage produces malformed marker names resulting in broken visible text in published articles.
**Migration:** Agent specifies placements as a structured array `[{ type, productId, after_paragraph }]`.
System resolves product data and generates widget HTML from site config.

### Requirement: Widget Presence (compliance)
**Reason:** Compliance validation is the agent's responsibility. System does not gate publish
on widget presence checks.
**Migration:** Agent is expected to include widget placements for all brief products. The publish
response warns if any product has 0 text mentions in the article.

---

## MODIFIED Requirements

### Requirement: Widget HTML Structure
Each rendered PriceRunner widget SHALL consist of:
1. A container `<div>` with a unique `id="pr-product-widget-{uuid}"`
2. An async `<script>` loading from `https://api.pricerunner.com/publisher-widgets/{countryLower}/product.js`
   with params: `onlyInStock=true`, `offerOrigin=NATIONAL`, `offerLimit=3`,
   `productId={numericId}`, `partnerId={urlEncodedPartnerId}`, `widgetId=pr-product-widget-{uuid}`
3. A required attribution `<div>` containing an `<a rel="sponsored">` link to the product URL
   with the text "Annonce i samarbejde med **PriceRunner**"

`uuid` SHALL be generated per widget instance via `crypto.randomUUID()`.
`numericId` SHALL be the product ID with the `pr_` prefix stripped.
`urlEncodedPartnerId` SHALL be `encodeURIComponent(siteConfig.pricerunnerPartnerId)`.
`countryLower` SHALL be the site config `pricerunnerCountry` in lowercase.
Product URLs from PriceRunner that are relative (`/pl/...`) SHALL be made absolute by
prepending the PriceRunner base URL for the site's country.
`rel="sponsored"` SHALL be used (not `rel="nofollow"` — Google's current affiliate standard).

If `productId` or `partnerId` is missing, the system SHALL fall back to:
`<p><a href="{absoluteUrl}" rel="sponsored" class="btn-primary">Se pris på {name}</a></p>`

#### Scenario: Widget generated for known product
- **WHEN** a placement `{ type: "widget", productId: "pr_3741515", after_paragraph: 3 }` is processed
- **THEN** system generates full widget HTML with numeric productId "3741515" inserted at paragraph 3

#### Scenario: Widget fallback — missing partnerId
- **WHEN** site config has no pricerunnerPartnerId
- **THEN** system inserts fallback button link instead of full widget HTML

---

## ADDED Requirements

### Requirement: Agent-directed placement
The system SHALL accept a `placements` array on publish and inject HTML blocks at the
specified paragraph positions in the Markdown source before Markdown→HTML conversion.
Placements SHALL be applied in descending `after_paragraph` order to preserve earlier indices.
If `after_paragraph` exceeds the paragraph count, the placement SHALL be appended at end-of-content.

#### Scenario: Image placed at paragraph 2
- **WHEN** placement `{ type: "image", productId: "pr_123", after_paragraph: 2 }` is provided
- **THEN** product image figure HTML is inserted after the second Markdown paragraph

#### Scenario: Paragraph index exceeds article length
- **WHEN** after_paragraph is 20 but article has only 10 paragraphs
- **THEN** placement is appended at end of article without error

---

### Requirement: Inline affiliate link conversion
After widget/image injection and Markdown→HTML conversion, the system SHALL scan the article
HTML for product name mentions and convert them to affiliate links.
- Matching SHALL be case-insensitive and word-boundary aware
- Maximum 2 links per product (additional mentions left as plain text)
- Mentions inside heading tags (`<h1>`–`<h6>`) SHALL NOT be converted
- Link format: `<a href="{absoluteAffiliateUrl}?partnerId={urlEncodedPartnerId}" rel="sponsored">`

#### Scenario: Product name mentioned twice
- **WHEN** article contains "Apple MacBook Air" twice in body paragraphs
- **THEN** both occurrences are converted to affiliate links

#### Scenario: Product name mentioned three times
- **WHEN** article contains a product name three times in body paragraphs
- **THEN** first two occurrences are linked, third is left as plain text

#### Scenario: Product name in heading
- **WHEN** article contains product name inside an `<h2>` tag
- **THEN** heading mention is NOT converted to a link
