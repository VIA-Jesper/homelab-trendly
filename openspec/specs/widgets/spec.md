# Widgets — Placement Engine and Affiliate Widget Rules

## Overview
The widget system uses an agent-directed placement engine. The agent specifies where
to inject images and widgets via a `placements` array — there are no inline placeholders
in the article text. `insertPlacements` is called before Markdown-to-HTML conversion.

## Requirements

### REQ-WIDGET-001 — Placement Input
`insertPlacements` SHALL accept an article string, a ContentBrief, a placements array, and
a siteKey. Each placement entry is: `{ type: "image" | "widget", productId: string, after_paragraph: number }`.

### REQ-WIDGET-002 — Insertion Order
Placements SHALL be sorted descending by `after_paragraph` before injection so that
earlier paragraph indices remain valid after each splice. If `after_paragraph` exceeds
the paragraph count, the block is appended at the end.

### REQ-WIDGET-003 — Image Block
An image placement SHALL render a `<figure>` element with:
- `<img src loading="lazy">` with rounded/shadow Tailwind classes
- `alt`: product name + brand (from specs), falling back to product name only
- `<figcaption>`: product name + retailer + price in DKK

### REQ-WIDGET-004 — PriceRunner Widget Block
A widget placement SHALL render the official PriceRunner JS embed widget.
Two variants are used, alternating by widget position in the article:
- 1st widget → `singleproduct.js` (lowest price, strong single CTA)
- 2nd widget → `product.js` (top 3 offers, good for alternatives)
- 3rd widget → `singleproduct.js`, and so on

Widget embed parameters: productId (numeric, strip "pr_" prefix), partnerId from site config,
widgetId (UUID per instance), country (from site config, lowercase).

The widget block SHALL include a sponsored disclosure link below the embed in compliance with
Danish marketing rules: `rel="sponsored nofollow"`.

### REQ-WIDGET-005 — Fallback Widget
If `pricerunnerPartnerId` is not configured for the site, the widget SHALL fall back to a
styled Tailwind card containing: product name, retailer, price in DKK, and a buy CTA link
with `rel="sponsored"`.

### REQ-WIDGET-006 — Unknown Product
If a placement references a product ID not found in the brief, the block is skipped
(empty string returned) and a warning is logged. No error is thrown.

## Scenarios

### Scenario: Widget placement injected
GIVEN an article with 5 paragraphs and a placement { type: "widget", productId: "pr_123", after_paragraph: 2 }
WHEN insertPlacements runs with a configured partnerId
THEN a PriceRunner singleproduct.js embed is injected after paragraph 2

### Scenario: Image placement injected
GIVEN a placement { type: "image", productId: "pr_456", after_paragraph: 0 }
WHEN insertPlacements runs
THEN a <figure> with lazy-loaded img and figcaption is injected after paragraph 0

### Scenario: Widget variant alternation
GIVEN 3 widget placements in the article
WHEN insertPlacements runs
THEN placements 1 and 3 use singleproduct.js and placement 2 uses product.js

### Scenario: No partner ID configured
GIVEN siteKey has no pricerunnerPartnerId
WHEN a widget placement is processed
THEN a Tailwind fallback card is rendered instead of the JS embed

### Scenario: Unknown product ID
GIVEN a placement references a productId not in the brief
WHEN insertPlacements processes it
THEN the placement is skipped with a console warning and no error is thrown
