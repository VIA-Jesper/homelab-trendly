# Affiliate Article Pipeline Skill

## Available tools
- `testflow_fetch_products` - fetch products from PriceRunner by category ID
- `testflow_inject_compliance` - add disclosure, ref params, and widget to HTML
- `testflow_deterministic_audit` - rule-based compliance check
- `testflow_create_draft` - create WordPress draft (REQUIRES APPROVAL)
- `testflow_record_run` - save run metadata to SQLite
- `testflow_published_titles` - get published article titles for internal linking
- `testflow_discover_categories` - search PriceRunner category tree

> If these tools are not in your tool list, the TestFlow plugin is not loaded.
> Tell the user to run `openclaw plugins install ./openclaw-plugin-testflow` and restart.

---

## Two input modes

### Mode A - Product-first (user gives product name(s))

| Products given | Signals | Template |
|---|---|---|
| 1 | (always) | `single-review` |
| 2 | "vs", "versus", "mod", "eller", "bedst" | `versus` |
| 2 | "sammenlign", "forskel", no clear signal | `comparison` |
| 3+ | "de bedste X", "top X", "anbefalinger" | `best-of-list` |
| 3+ | named specific products, no ranking intent | `comparison` |

**Resolution steps:**
1. Count products and read intent signals - pick template from table above
2. Identify product category using your knowledge
3. Look up category ID in `sites/pricerunner-categories.yaml`
4. If not found, call `testflow_discover_categories(query)` with Danish product type name
5. Generate natural Danish `topic` and `keyword`
6. Set `explicit_products` to the user's product names

### Mode B - Intent-first (user describes what they want)

| Type | When to use |
|---|---|
| `best-of-list` | "de bedste X", category ranking |
| `buying-guide` | "hvordan vaelger jeg X", "guide til X" |
| `single-review` | review one specific product |
| `versus` | compare exactly 2 products |
| `comparison` | compare 3+ specific products |

---

## Parameter resolution rules
- `topic`: a natural, clickable Danish article title
- `keyword`: primary SEO keyword in Danish
- `category_id`: numeric PriceRunner category ID from `sites/pricerunner-categories.yaml`
- `explicit_products`: always populate when user named specific products; empty for category articles
- `site`: default to `"sites/site-one.yaml"` unless specified

---

## Pipeline execution

### Step 0 - Fetch products
```
testflow_fetch_products(category_id=<id>, limit=10, explicit_products=[...])
-> { "products": [ { "name", "price_min", "affiliate_url", "image_url", "rating" } ] }
```
If 0 products returned: tell the user and stop.

### Step 1 - Brief loop (max 2 attempts)
Reason inline. Produce a ContentBrief JSON:
```json
{
  "topic": "...", "keyword": "...", "article_type": "...",
  "target_word_count": 1200, "key_angles": ["..."],
  "product_order": ["Product A", "Product B"],
  "outline": ["## Section 1", "## Section 2"]
}
```
Review inline: Is topic clickable in Danish? Does outline match template? Min 3 distinct angles?
If score < 7/10: note issues, retry with feedback. After 2 failed attempts: tell user, stop.

### Step 2 - Article loop (max 3 attempts)
Write full article HTML. Must include:
- `<div class="affiliate-disclosure">` as the very first element
- All PriceRunner links use `affiliate_url` from product data (already has `?ref-site=`)
- `rel="sponsored nofollow"` and `target="_blank"` on all PriceRunner links
- NO prohibited claims: "billigste pris garanteret", "laveste pris", "garanti for", "vi garanterer"
- PriceRunner widget: `<div class="pr-widget" data-category="<category_id>"></div>`
- `yoast_meta`: `{ focus_keyword, seo_title, meta_description }`

Produce ArticleDraft JSON:
```json
{
  "title": "...", "slug": "...", "body_html": "...",
  "yoast_meta": { "focus_keyword": "...", "seo_title": "...", "meta_description": "..." },
  "categories": ["Kategori"], "tags": ["tag1"],
  "featured_image_url": "https://cdn.pricerunner.dk/..."
}
```
Review inline: disclosure present? links compliant? Score 0-10.
If score < 7/10 or hard fail: retry with specific issues. After 3 attempts: tell user, stop.

### Step 3 - SEO + CRO pass (max 1 retry)
**SEO:** Update heading structure (H1/H2/H3), keyword in H1 and intro, add 2-3 internal links
(call `testflow_published_titles(site_name="site_one")` for existing titles).

**CRO:** Review CTA placement, product ordering (best value first), min 1 CTA per 400 words.

Review inline: keyword stuffed? headings logical? CTAs well-placed?
If failed: retry once with specific issues. After 2 total attempts: tell user this needs human review, stop.

### Step 4 - Deterministic compliance
```
testflow_inject_compliance(html=<body_html>, affiliate_id=<from env>, partner_id=<from env>)
-> { "html": "...", "transforms_applied": N }

testflow_deterministic_audit(html=<result html>)
-> { "passed": true|false, "errors": [...], "warnings": [...] }
```
If `passed: false`: log errors, tell user, stop. Do NOT call `testflow_create_draft`.

### Step 5 - Publish draft
```
testflow_create_draft(article={...ArticleDraft with updated body_html...}, site="sites/site-one.yaml")
-> { "post_id": 123, "post_url": "https://..." }
```
> `testflow_create_draft` will pause and ask for your approval before calling WordPress.
> Approve or deny in the chat. Timeout (5 min) = auto-deny.

```
testflow_record_run(run_id=<uuid>, topic=..., keyword=..., category_id=N, article_type=..., status="success")
```

Tell the user: "Draft created: <post_url> - open WP Admin to review and publish."

---

## What you must NEVER do
- Guess a category ID. Always read from `pricerunner-categories.yaml` or call `testflow_discover_categories`.
- Publish directly. All articles go as WP drafts. The human publishes manually.
- Skip the deterministic audit. Always call it, even if the article looks clean.
- Make up product URLs. Always use `affiliate_url` from the fetched product data.
