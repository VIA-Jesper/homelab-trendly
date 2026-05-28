# MVP Implementation Plan: Autonomous Affiliate Marketing WordPress Site Generator

**Date:** 2026-05-27
**Project:** TestFlow
**Scope:** MVP 1 - Single-site working pipeline

---

## Skills / Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Core language |
| Poetry | 1.8+ | Dependency management |
| WordPress | 6.4+ | Target CMS |
| WP Application Passwords | Built-in (WP 5.6+) | REST API auth |
| Yoast SEO plugin | Latest | SEO fields on WP |
| OpenClaw | Latest | Primary orchestrator agent (provides LLM + sub-agent tooling) |
| SQLite | 3.x | State database (no server needed) |
| httpx | 0.27+ | Async HTTP client |
| Pydantic | 2.x | Data models and validation |
| python-dotenv | Latest | Secret management |
| PyYAML | Latest | Site config files |
| BeautifulSoup4 | 4.12+ | HTML parsing for compliance engine |
| FastAPI + uvicorn | 0.111+ / 0.30+ | Optional: expose tools as HTTP endpoints |

---

## 1. System Architecture Overview

```
+------------------------------------------------------------------+
|                    OPENCLAW (the brain)                          |
|                                                                  |
|  Reads: skills/affiliate-pipeline.md  (instruction set)         |
|  Reads: sites/pricerunner-categories.yaml  (category IDs)       |
|                                                                  |
|  Phase 1 - Brief     : inline reasoning → ContentBrief JSON     |
|  Phase 2 - Article   : inline reasoning → ArticleDraft JSON     |
|  Phase 3 - SEO/CRO  : inline reasoning → updates draft          |
|  Reviews             : inline reasoning → ReviewReport JSON     |
|  Tool calls          : native plugin tools (testflow_*) between   |
|                        steps - no web_fetch needed               |
|  Retry logic         : OpenClaw decides retry/abort natively    |
|  Sub-agents          : optional (Phase 2) via sessions_spawn    |
+------------------------------------------------------------------+
          |
          | calls Python tools (deterministic - no LLM inside)
          v
+------------------------------------------------------------------+
|  OPENCLAW TOOL PLUGIN  (openclaw-plugin-testflow, TypeScript)   |
|                                                                  |
|  testflow_fetch_products(category_id, limit, explicit_products) |
|  testflow_inject_compliance(html, affiliate_id, partner_id)     |
|  testflow_deterministic_audit(html)                             |
|  testflow_create_draft(article, site)  ← requires approval gate |
|  testflow_record_run(run_id, topic, ...)                        |
|  testflow_published_titles(site_name)                           |
+------------------------------------------------------------------+
          |
          | internal HTTP calls to Python tool server
          v
+------------------------------------------------------------------+
|  PYTHON TOOL SERVER  (tool_server.py / FastAPI on :8000)        |
|                                                                  |
|  fetch_products_by_category(category_id) ──────────> PriceRunner|
|  inject_compliance(html)     - BeautifulSoup4, adds ref params  |
|  deterministic_audit(html)   - safety checks, returns pass/fail |
|  create_draft(article, site) - WP REST API, returns draft URL   |
|  record_run(...)             - SQLite state logging             |
+------------------------------------------------------------------+
          |
          | WP REST API + Yoast REST Bridge
          v
+------------------------------------------------------------------+
|  WORDPRESS SITE                                                  |
|  WP REST API  /wp/v2/posts  /wp/v2/media  /wp/v2/categories     |
|  Yoast REST Bridge plugin  /yoast-bridge/v1/post/{id}/meta      |
+------------------------------------------------------------------+
```

**Design principle:** OpenClaw IS the orchestrator AND the LLM. It does all reasoning (brief generation, article writing, reviews, SEO/CRO optimization) using its own intelligence. The Python layer contains ZERO LLM calls - it only does deterministic I/O (HTTP, DB, filesystem). No external LLM API keys or runtime adapters needed.

**Why the plugin layer?** A native OpenClaw tool plugin means OpenClaw calls tools by name (`testflow_create_draft(...)`) rather than making raw HTTP requests described in the skill doc. Benefits:
- Tools show up in OpenClaw's tool catalog (`/tools` command)
- Parameter schemas are typed with TypeBox - OpenClaw knows exactly what to pass
- No need for `web_fetch` in the skill doc; cleaner skill document
- The plugin's `before_tool_call` hook provides a proper **human approval gate** before any WordPress publish call
- `testflow_create_draft` is marked `optional: true` (user must explicitly allowlist it) for safety

**Why keep the Python server?** The tools use BeautifulSoup4 (Python-only), SQLite, and httpx. The TypeScript plugin is a thin HTTP wrapper - all business logic stays in Python. Both servers run locally: FastAPI on `:8000`, OpenClaw plugin loaded by OpenClaw daemon.

---

## 1b. Layer Overview - What each script does and why we need it

### TypeScript layer (`openclaw-plugin-testflow/`)

**Purpose:** Pure adapter. Zero business logic. Exists only to integrate with OpenClaw.

| File | What it does | Why it must exist |
|------|-------------|-------------------|
| `client.ts` | Two HTTP helper functions: `callTool(path, body)` for POST, `getTool(path)` for GET. Both call `http://localhost:8000`. That's literally all it does. | The TypeScript plugin can't directly run Python code - it bridges to the Python server via HTTP. |
| `index.ts` | Registers 6 `testflow_*` tools with TypeBox parameter schemas. Adds a `before_tool_call` hook that pauses before `testflow_create_draft` and asks for human approval. | OpenClaw plugins **must** be TypeScript/Node.js. Only way to register native tools in OpenClaw's tool catalog and use the hook system. Without this, OpenClaw would have to call raw HTTP URLs and could not gate on approval. |

**The TypeScript layer is intentionally thin.** If you change any tool logic, you never touch TypeScript - you change Python. The TypeScript just relays calls.

---

### Python layer (`src/testflow/` + `tool_server.py`)

**Purpose:** All real work - I/O, HTML parsing, database writes, HTTP clients.

| File | What it does | Why Python |
|------|-------------|-----------|
| `tool_server.py` | FastAPI server on `:8000`. Exposes `/tools/*` POST endpoints. Imports and calls the `tools.py` functions. Returns JSON. | Glue - serves the TypeScript plugin's HTTP requests. FastAPI gives automatic validation + `/docs` for free. |
| `content/pricerunner.py` | `PriceRunnerClient` - fetches product data from PriceRunner's unofficial API. UA rotation, rate limiting with jitter, 429 backoff, 24h disk cache. | `httpx` for HTTP, `tenacity` for retries. No good TS equivalent with the same robustness. |
| `publisher/client.py` | `WordPressClient` - creates WP draft posts, sideloads images, sets Yoast meta via the bridge plugin. Resolves category/tag names to IDs idempotently. | `httpx`, base64 auth. Python is simpler here than a TS alternative. |
| `compliance/link_injector.py` | Scans all `<a>` tags in article HTML. Adds `?ref-site=` to every PriceRunner link. Adds `rel="sponsored nofollow"` and `target="_blank"`. | **BeautifulSoup4** - only good HTML parser for this job. Python-only. |
| `compliance/disclosure.py` | Inserts the Danish affiliate disclosure `<div class="affiliate-disclosure">` as the first child of the article body. | **BeautifulSoup4** - reliable DOM manipulation. |
| `compliance/widget_injector.py` | Checks that the PriceRunner JS widget block (`<div class="pr-widget">`) is present. Inserts it after the intro paragraph if missing. | **BeautifulSoup4** |
| `compliance/rules.py` | Exports `COMPLIANCE_RULES` dict - single source of truth for what must be in every article. Passed into both the OpenClaw article prompt AND `deterministic_audit()`. | Keeping rules in one place prevents drift between what OpenClaw is told to write and what the audit checks. |
| `compliance/inject_compliance.py` | Runs all three transforms in sequence: link injection → disclosure → widget. Called after OpenClaw approves the article draft. | Orchestrates the three BS4 modules in the right order. |
| `orchestration/tools.py` | Entry-point functions (`fetch_products_by_category`, `inject_compliance`, `deterministic_audit`, `create_draft`, `record_run`, `get_published_titles`) called by `tool_server.py`. | Thin coordinators - import the right client/module and return JSON-serializable results. |
| `db.py` | SQLite schema + `record_run()` and `record_review_attempt()` functions. Writes to `testflow_state.db`. | `sqlite3` is built into Python. Zero setup, zero dependencies, perfect for a local state log. |
| `models.py` | Pydantic models: `PRProduct`, `ContentBrief`, `ArticleDraft`, `ReviewReport`, `SiteConfig`, etc. | Data validation at every boundary. JSON schemas match what OpenClaw produces and what tool_server.py accepts. |

**Why Python for all of this?** BeautifulSoup4 has no TS equivalent at the same maturity. `sqlite3` is built-in. `pydantic` v2 is faster and stricter than most TS validation libs. `httpx` handles retry and timeout cleanly. These are all the right tools for these jobs.

---

### Data flow for one article

The full pipeline is strictly sequential. OpenClaw works through each phase using its own reasoning. Python tools are called at the deterministic steps.

```
Human instruction (free text)  →  OpenClaw reads skill document
                                   ↓ resolves params (product count + intent signals)
  OpenClaw begins pipeline: article_type, topic, keyword, category_id, explicit_products, site
  |
  +-- [tool] fetch_products_by_category(category_id, limit=10)
  |       -> list[PRProduct { name, price_min, url, image_url, affiliate_url }]
  |       (+ filter by explicit_products if versus/single-review)
  |
  +----- BRIEF LOOP (max 2 retries) -----+
  |                                                    |
  |  OpenClaw — Brief phase context:                  |
  |    "You are writing a content brief.              |
  |     Topic: {topic}, Keyword: {keyword}            |
  |     Products: {product_list}                      |
  |     Template: {template_yaml}                     |
  |     Previous feedback: {feedback or 'none'}"      |
  |  → OpenClaw produces ContentBrief JSON            |
  |                                                   |
  |  OpenClaw — Brief Review context:                 |
  |    "Review this brief against these criteria..."  |
  |  → OpenClaw produces ReviewReport JSON            |
  |    passed? → Article Loop                         |
  |    failed? → retry with feedback injected         |
  +----------------------------------------------------+
  |
  +----- ARTICLE LOOP (max 3 retries) -----------------+
  |                                                    |
  |  OpenClaw — Article phase context:                |
  |    "You are writing an affiliate article.         |
  |     Approved brief: {brief_json}                  |
  |     Products: {products_with_images}              |
  |     Template: {template_yaml}                     |
  |     Compliance rules: {rules}                     |
  |     Previous feedback: {feedback or 'none'}"      |
  |  → OpenClaw produces ArticleDraft JSON            |
  |                                                   |
  |  OpenClaw — Article Review context:               |
  |    "Review this draft against brief + compliance" |
  |  → OpenClaw produces ReviewReport JSON            |
  |    passed? → Optimization Loop                    |
  |    failed? → retry with structured issues[]       |
  +----------------------------------------------------+
  |
  +----- OPTIMIZATION LOOP (max 1 retry) ---------------+
  |                                                     |
  |  OpenClaw — SEO phase context:                     |
  |    "Optimise this article for search..."           |
  |  → OpenClaw returns updated ArticleDraft           |
  |                                                    |
  |  OpenClaw — CRO phase context:                     |
  |    "Optimise this article for conversion..."       |
  |  → OpenClaw returns updated ArticleDraft           |
  |                                                    |
  |  OpenClaw — Optimization Review context:           |
  |    "Check SEO/CRO didn't introduce problems..."   |
  |  → passed? → continue                             |
  |    failed + retry? → re-run SEO+CRO with issues[] |
  |    failed + no retries? → abort, flag human        |
  +-----------------------------------------------------+
  |
  +-- [tool] inject_compliance(html)    # deterministic transforms
  +-- [tool] deterministic_audit(html)  # safety net - abort if fails
  +-- [tool] create_draft(article, site) # creates WP draft only
  +-- [tool] record_run(...)
```

> **Internal linking note:** OpenClaw's SEO phase adds 2-3 outbound internal links FROM the new article TO existing relevant articles. No post-publish link pass is needed in the generation pipeline. The reverse direction (old articles linking to new) is handled by `optimizer.py` as a periodic maintenance task - run it manually when the site has enough articles to make it worthwhile (20+).

**Why sequential, not parallel?**
SEO may restructure headings and reorder sections. CRO must work with that final structure. Each phase is the input to the next.

**Reviewer placement rationale:**
- Brief and Article loops have full retry reviews (generation can be bad, worth iterating)
- SEO and CRO are narrow passes - a single combined Optimization Review after both is sufficient
- The Optimization Review gets **one retry**: on fail, structured `issues[]` are passed back to SEO and CRO on the second pass. If it still fails, the pipeline aborts and flags for human review.

**Max retries:** Brief loop: 2. Article loop: 3. Score threshold: configurable (default 7/10).

---

### OpenClaw reasoning phases (what `prompts.py` builds)

OpenClaw does not call external LLMs. It IS the LLM. Each "phase" is OpenClaw shifting context to a specific task. `prompts.py` builds the context string for each phase - OpenClaw reads it and produces the output.

---

**Brief phase — context string for OpenClaw**
```
TASK: Create a content brief for an affiliate article
TOPIC: {topic}
KEYWORD: {keyword}
ARTICLE TYPE: {template.type}   e.g. best-of-list, comparison, buying-guide
PRODUCTS AVAILABLE: {product_list_json}
SITE RULES: {site_config.rules}
PREVIOUS FEEDBACK: {reviewer_feedback or "none"}

Return ONLY valid JSON:
{
  "angle": "unique editorial angle for this article",
  "tone": "friendly/expert/neutral",
  "products_to_feature": ["product_name", ...],
  "outline": [
    { "section": "Intro", "purpose": "...", "target_words": 150 },
    { "section": "Top picks", "purpose": "...", "target_words": 400 },
    ...
  ],
  "key_claims": ["concrete claim 1", ...],
  "seo_title": "max 60 chars",
  "meta_description": "max 155 chars",
  "focus_keyword": "primary keyword"
}
```

---

**Brief Review phase — context string for OpenClaw**
```
TASK: Review this content brief
BRIEF: {content_brief_json}
CRITERIA:
  - Angle is distinctive, not generic
  - Outline covers all required sections for article type: {template.required_sections}
  - Key claims are specific and verifiable (no vague superlatives)
  - Product selection is relevant to the keyword
  - SEO title and meta description fit within character limits

Return ONLY valid JSON: { "passed": bool, "score": 0-10, "feedback": "...", "issues": [] }
```

---

**Article generation phase — context string for OpenClaw**
```
TASK: Write an affiliate article from this approved brief
APPROVED BRIEF: {content_brief_json}
ARTICLE TEMPLATE: {template_yaml}
PRODUCTS: {product_list_json}
COMPLIANCE RULES: {compliance_rules}
PREVIOUS FEEDBACK: {reviewer_feedback or "none"}

Return ONLY valid JSON matching ArticleDraft schema. No markdown fences.
```

---

**Article review phase — context string for OpenClaw**
```
TASK: Review this affiliate article draft
DRAFT: {article_draft_json}
APPROVED BRIEF: {content_brief_json}  (check article matches the brief)
TEMPLATE: {template.required_sections}
QUALITY CRITERIA:
  - Reads naturally, not like AI spam
  - Intro establishes genuine user need (min 150 words)
  - Each product has specific, concrete details (not generic)
  - Structure matches the approved brief outline
  - CTA is clear and not aggressive
COMPLIANCE CRITERIA:
  - All pricerunner.dk links have rel="sponsored nofollow"
  - Affiliate disclosure present at top
  - PriceRunner widget present
  - Yoast fields populated and within character limits
  - No prohibited claims

Return ONLY valid JSON:
{ "passed": bool, "score": 0-10, "feedback": "...",
  "issues": [{ "type": "...", "severity": "blocker|quality", "fix": "..." }] }
```

*(Structured issues let the Generator fix specific problems on retry, not just read a wall of notes.)*

---

**SEO phase — context string for OpenClaw** *(single pass)*
```
TASK: Optimise this article for search
DRAFT: {article_draft_json}
PRIMARY KEYWORD: {keyword}
SECONDARY KEYWORDS: {related_keywords}
SITE: {site_config.name}

Tasks:
  - Ensure H1 contains primary keyword
  - H2/H3 hierarchy is logical and keyword-rich
  - First paragraph contains keyword naturally
  - Meta description is compelling and within 155 chars
  - Suggest 2-3 internal links (titles only - orchestrator resolves them from DB)
  - Confirm schema_type is correct for article type

Return updated ArticleDraft JSON with SEO improvements applied.
```

---

**CRO phase — context string for OpenClaw** *(single pass)*
```
TASK: Optimise this article for conversion
DRAFT: {article_draft_json}  (already SEO-optimised)
ARTICLE TYPE: {template.type}
AFFILIATE NETWORK: PriceRunner

Tasks:
  - Ensure primary CTA appears above the fold and after comparison section
  - Product order: highest-converting / best-value first (if no data, use price/quality ratio)
  - Add urgency signal where appropriate (e.g. price comparison context)
  - Ensure each product has a clear action link (not just a widget)
  - Trust signals: check that pros/cons are balanced and honest
  - Button/link copy is action-oriented ("Se pris", "Sammenlign priser")

Return updated ArticleDraft JSON with CRO improvements applied.
```

---

**Optimization review phase — context string for OpenClaw** *(single pass after SEO + CRO)*
```
TASK: Review this article after SEO and CRO optimisation
DRAFT: {cro_optimised_draft_json}
ORIGINAL APPROVAL SCORE: {article_reviewer_score}  (baseline to compare against)

Check that SEO and CRO optimisation did NOT introduce:
  - Keyword stuffing or unnatural repetition of the focus keyword
  - Headings that no longer match the article content
  - Aggressive, misleading, or legally problematic urgency copy
  - Broken compliance: missing disclosure, broken rel attributes, widget removed
  - Loss of quality: sections removed, content significantly shortened without reason
  - CTA language that implies guarantees ("billigste pris garanteret" etc.)

If optimisation improved the article without the above issues: pass.
If issues are found: fail with specific issues listed. Do NOT retry - flag for human review.

Return ONLY valid JSON:
{ "passed": bool, "score": 0-10, "feedback": "...",
  "issues": [{ "type": "...", "severity": "blocker|warning", "fix": "..." }] }
```

---

## 2. Project Folder Structure

```
TestFlow/
├── pyproject.toml                # Python deps + ruff/mypy/pytest/taskipy config
├── .env                          # secrets (gitignored)
├── .env.example                  # full annotated template - copy to .env and fill in
├── .gitignore
├── config.json5                  # OpenClaw project config (profile, plugin, tool allowlist)
├── PLAN.md                       # implementation plan (copy of ~/.augment/plans/plan-*.md)
├── README.md
├── AGENTS.md                     # OpenClaw project entry point - read on startup
├── runner.py                     # CLI helper (human can trigger pipeline manually)
├── optimizer.py                  # CLI entry point (optimization pipeline)
├── tool_server.py                # FastAPI server - exposes Python tools to OpenClaw via HTTP
├── scripts/
│   ├── start.sh                  # Start tool server + health check
│   └── build-plugin.sh           # Rebuild + reinstall the OpenClaw TS plugin after changes
├── openclaw-plugin-testflow/
│   ├── package.json              # npm: build scripts, openclaw + typebox deps
│   ├── tsconfig.json             # TypeScript: NodeNext, outDir=dist, strict
│   └── src/
│       ├── index.ts              # definePluginEntry: tool registrations + approval hook
│       └── client.ts             # callTool/getTool HTTP helpers -> Python server
├── sites/
│   ├── site-one.yaml                   # Site 1 config (used for testing)
│   ├── site-two.yaml                   # Site 2 config (ready, not used in MVP tests)
│   └── pricerunner-categories.yaml     # keyword → category ID mapping (orchestrator uses this)
├── affiliate/
│   └── config.yaml               # Affiliate rules (ref params, widgets, disclosure)
├── templates/
│   ├── best-of-list.yaml         # "Bedste X produkter" structure
│   ├── single-review.yaml        # Deep single-product review
│   ├── comparison.yaml           # Side-by-side product comparison
│   ├── buying-guide.yaml         # Educational guide + recommendations
│   └── versus.yaml               # Head-to-head: Product A vs B
├── src/
│   └── testflow/
│       ├── __init__.py
│       ├── models.py             # Pydantic: Article, YoastMeta, SiteConfig, etc.
│       ├── db.py                 # SQLite state DB
│       ├── publisher/
│       │   ├── __init__.py
│       │   ├── client.py         # WP REST API client (httpx)
│       │   └── yoast.py          # Yoast bridge calls
│       ├── content/
│       │   ├── __init__.py
│       │   ├── pricerunner.py    # PriceRunner product data fetcher + category discovery
│       │   └── keywords.py       # Keyword stub (returns placeholder; Phase 3: Ahrefs API)
│       ├── compliance/
│       │   ├── __init__.py
│       │   ├── rules.py              # COMPLIANCE_RULES - single source of truth
│       │   ├── link_injector.py      # Pricerunner ref param enforcement
│       │   ├── widget_injector.py
│       │   ├── disclosure.py
│       │   └── inject_compliance.py  # Runs all transforms post-review-approval
│       └── orchestration/
│           ├── __init__.py
│           ├── tools.py          # Deterministic tools (fetch, publish, record, audit) - exposed via tool_server.py
│           ├── prompts.py        # Context string builders for each OpenClaw reasoning phase
│           ├── templates.py      # Template loader: load_template(type) -> ArticleTemplate
│           ├── pipeline.py       # Sequential pipeline coordinator (used by tool_server.py run endpoint)
│           ├── logging.py        # Structured JSON logging + PipelineRunStats
│           └── scheduler.py      # Article scheduling logic (Phase 2)
├── wp-plugin/
│   └── yoast-rest-bridge/
│       ├── yoast-rest-bridge.php
│       └── includes/
│           └── endpoints.php
└── tests/
    ├── test_compliance.py
    ├── test_publisher.py
    ├── test_pricerunner.py
    └── test_tool_server.py
```

---

## 3. Article Template System

Templates are YAML files in `templates/`. They define the structural contract for each article type - required sections in order, word count targets, required elements, tone, and Yoast schema type. The Brief Generator picks the right template (or the orchestrator specifies it). The Article Generator receives the template verbatim and must follow it.

This means the Generator never has to decide structure - it only writes content. The template is the wheel; the Generator just turns it.

### Template schema (all 5 templates)

```yaml
# templates/best-of-list.yaml
type: best-of-list
display_name: "Bedste X produkter"
schema_type: Article
tone_guidance: "Helpful and concrete. The reader wants a clear recommendation."
min_products: 3
max_products: 8

required_sections:
  - id: intro
    heading: "Hvad skal du kigge efter?"
    purpose: "Establish user need and why this comparison is useful"
    target_words: 150
    required_elements: []

  - id: top_picks
    heading: "De bedste {keyword} - vores valg"
    purpose: "Ranked product list with widget per product"
    target_words: 600
    required_elements:
      - pricerunner_widget     # one widget per product
      - product_pros_cons      # bullet pros/cons per product
      - affiliate_link         # one outbound link per product

  - id: comparison_table
    heading: "Sammenligning"
    purpose: "Side-by-side table of key specs"
    target_words: 50
    required_elements:
      - html_table

  - id: buying_guide
    heading: "Sådan vælger du"
    purpose: "Educational: what criteria matter and why"
    target_words: 300
    required_elements: []

  - id: conclusion
    heading: "Vores anbefaling"
    purpose: "Clear winner + CTA"
    target_words: 100
    required_elements:
      - cta_button
```

```yaml
# templates/single-review.yaml
type: single-review
display_name: "Anmeldelse af X"
schema_type: Review
tone_guidance: "Honest, hands-on reviewer. Balance pros and cons. Give a clear verdict."
min_products: 1
max_products: 1

required_sections:
  - id: intro
    heading: "Hvad er {product_name}?"
    purpose: "Brief product intro - what is it, who is it for, why read this review"
    target_words: 120
    required_elements: []

  - id: specs
    heading: "Specifikationer"
    purpose: "Key technical specs in a table - objective facts, no opinion"
    target_words: 80
    required_elements:
      - html_table
      - pricerunner_widget

  - id: in_practice
    heading: "Sådan fungerer det i praksis"
    purpose: "Real-world use: what works, what doesn't, who it suits"
    target_words: 400
    required_elements: []

  - id: pros_cons
    heading: "Fordele og ulemper"
    purpose: "Structured pros and cons list"
    target_words: 100
    required_elements:
      - product_pros_cons

  - id: verdict
    heading: "Vores dom"
    purpose: "Clear recommendation with score or verdict, CTA to PriceRunner"
    target_words: 120
    required_elements:
      - affiliate_link
      - cta_button
```

```yaml
# templates/versus.yaml
type: versus
display_name: "X vs Y"
schema_type: Article
tone_guidance: "Direct and decisive. Pick a winner in each category. Give an overall pick."
min_products: 2
max_products: 2

required_sections:
  - id: intro
    heading: "{product_a} vs {product_b} - hvad er forskellen?"
    purpose: "Frame the comparison - who each product is for"
    target_words: 150
    required_elements: []

  - id: side_by_side
    heading: "Sammenligning"
    purpose: "Side-by-side spec table"
    target_words: 60
    required_elements:
      - html_table

  - id: product_a_section
    heading: "{product_a}"
    purpose: "Deep dive on product A - strengths, weaknesses, ideal user"
    target_words: 300
    required_elements:
      - pricerunner_widget
      - affiliate_link

  - id: product_b_section
    heading: "{product_b}"
    purpose: "Deep dive on product B - strengths, weaknesses, ideal user"
    target_words: 300
    required_elements:
      - pricerunner_widget
      - affiliate_link

  - id: verdict
    heading: "Hvem vinder?"
    purpose: "Category-by-category winners then an overall pick with rationale"
    target_words: 150
    required_elements:
      - cta_button
```

```yaml
# templates/comparison.yaml
type: comparison
display_name: "X vs Y vs Z"
schema_type: Article
tone_guidance: "Analytical and structured. Each product gets a fair assessment before the ranking."
min_products: 3
max_products: 5

required_sections:
  - id: intro
    heading: "Hvad vi sammenligner"
    purpose: "Why these specific products, what criteria matter"
    target_words: 130
    required_elements: []

  - id: comparison_table
    heading: "Hurtig oversigt"
    purpose: "Summary spec table across all products"
    target_words: 50
    required_elements:
      - html_table

  - id: product_reviews
    heading: "Produkterne i detaljer"
    purpose: "One subsection per product with widget, pros/cons, and affiliate link"
    target_words: 250          # per product - Generator multiplies by product count
    required_elements:
      - pricerunner_widget     # per product
      - product_pros_cons      # per product
      - affiliate_link         # per product

  - id: verdict
    heading: "Vores rangering"
    purpose: "Ranked list 1 to N with brief rationale per product"
    target_words: 150
    required_elements:
      - cta_button
```

```yaml
# templates/buying-guide.yaml
type: buying-guide
display_name: "Sådan vælger du X"
schema_type: Article
tone_guidance: "Educational and helpful. Teach first, recommend second. No pressure."
min_products: 2
max_products: 5

required_sections:
  - id: intro
    heading: "Hvad skal du kigge efter i en {category}?"
    purpose: "Why this guide exists, who it's for"
    target_words: 120
    required_elements: []

  - id: criteria
    heading: "De vigtigste faktorer"
    purpose: "Explain 3-5 key buying criteria with brief rationale each"
    target_words: 400
    required_elements: []

  - id: recommendations
    heading: "Vores anbefalinger"
    purpose: "2-5 product recommendations matching different buyer profiles"
    target_words: 350
    required_elements:
      - pricerunner_widget     # per recommended product
      - affiliate_link         # per recommended product

  - id: conclusion
    heading: "Hvad er det rigtige valg for dig?"
    purpose: "Decision matrix or summary matching buyer need to recommended product"
    target_words: 150
    required_elements:
      - cta_button
```

### Available templates

| Type | File | Min products | Max products | WP schema |
|------|------|------|------|------|
| `best-of-list` | `best-of-list.yaml` | 3 | 8 | Article |
| `single-review` | `single-review.yaml` | 1 | 1 | Review |
| `versus` | `versus.yaml` | 2 | 2 | Article |
| `comparison` | `comparison.yaml` | 3 | 5 | Article |
| `buying-guide` | `buying-guide.yaml` | 2 | 5 | Article |

### `src/testflow/orchestration/templates.py`

```python
from pathlib import Path
import yaml
from pydantic import BaseModel

class TemplateSection(BaseModel):
    id: str
    heading: str
    purpose: str
    target_words: int
    required_elements: list[str] = []

class ArticleTemplate(BaseModel):
    type: str
    display_name: str
    schema_type: str
    tone_guidance: str
    min_products: int
    max_products: int
    required_sections: list[TemplateSection]

TEMPLATES_DIR = Path("templates")

def load_template(article_type: str) -> ArticleTemplate:
    path = TEMPLATES_DIR / f"{article_type}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown article type: {article_type}. Available: {list_templates()}")
    return ArticleTemplate(**yaml.safe_load(path.read_text()))

def list_templates() -> list[str]:
    return [p.stem for p in TEMPLATES_DIR.glob("*.yaml")]
```

### How template type is chosen

**Template is always decided by the orchestrator - never by the Brief Generator.**
The Brief Generator is a content writer, not a strategist. It receives a template and follows it.

**Mode A (product-first) - orchestrator resolves template from product count + intent signals:**

| Products given | Default template | Can it be different? |
|---|---|---|
| 1 | `single-review` | No - only makes sense as a review |
| 2 | `versus` OR `comparison` | Yes - orchestrator reads intent signals (see below) |
| 3+ | `comparison` OR `best-of-list` | Yes - orchestrator reads intent signals (see below) |

**Intent signal rules for the orchestrator (Mode A):**

For 2 products:
- Contains "vs", "versus", "mod", "eller" → `versus` (battle format, picks a winner)
- Contains "sammenlign", "forskel", "difference" → `comparison` (balanced analysis)
- No clear signal → default to `versus` and mention the choice to the user

For 3+ products:
- User named specific products explicitly → `comparison` (they picked the contenders)
- User asked for "de bedste X", "top X", "anbefalinger" → `best-of-list` (category ranking)
- No clear signal → default to `comparison`

**Mode B (intent-first):** The orchestrator forces a specific template via `--template` flag. No inference needed.

**The Brief Generator's job:** Receive the template decided by the orchestrator. Execute it. Never propose a different template type.

---

### `wp-plugin/yoast-rest-bridge/yoast-rest-bridge.php`

```php
<?php
/**
 * Plugin Name: Yoast SEO REST Bridge
 * Description: Exposes Yoast SEO fields via WP REST API for automated publishing.
 * Version: 1.0.0
 */
if ( ! defined( 'ABSPATH' ) ) exit;
require_once plugin_dir_path( __FILE__ ) . 'includes/endpoints.php';
```

### `wp-plugin/yoast-rest-bridge/includes/endpoints.php`

```php
<?php
add_action( 'rest_api_init', function () {
    register_rest_route( 'yoast-bridge/v1', '/post/(?P<id>\d+)/meta', [
        [ 'methods' => 'GET',  'callback' => 'yrb_get_yoast_meta', 'permission_callback' => 'yrb_auth' ],
        [ 'methods' => 'POST', 'callback' => 'yrb_set_yoast_meta', 'permission_callback' => 'yrb_auth' ],
    ] );
} );

function yrb_auth(): bool { return current_user_can( 'edit_posts' ); }

function yrb_yoast_keys(): array {
    return [
        'focus_keyword'    => '_yoast_wpseo_focuskw',
        'meta_description' => '_yoast_wpseo_metadesc',
        'seo_title'        => '_yoast_wpseo_title',
        'canonical'        => '_yoast_wpseo_canonical',
        'schema_type'      => '_yoast_wpseo_schema_page_type',
        'no_index'         => '_yoast_wpseo_meta-robots-noindex',
    ];
}

function yrb_get_yoast_meta( WP_REST_Request $request ): WP_REST_Response {
    $post_id = (int) $request->get_param( 'id' );
    $data = [];
    foreach ( yrb_yoast_keys() as $friendly => $meta_key ) {
        $data[ $friendly ] = get_post_meta( $post_id, $meta_key, true );
    }
    return new WP_REST_Response( $data, 200 );
}

function yrb_set_yoast_meta( WP_REST_Request $request ): WP_REST_Response {
    $post_id = (int) $request->get_param( 'id' );
    $body    = $request->get_json_params();
    $updated = [];
    foreach ( yrb_yoast_keys() as $friendly => $meta_key ) {
        if ( isset( $body[ $friendly ] ) ) {
            update_post_meta( $post_id, $meta_key, sanitize_text_field( $body[ $friendly ] ) );
            $updated[ $friendly ] = $body[ $friendly ];
        }
    }
    return new WP_REST_Response( [ 'updated' => $updated ], 200 );
}
```

**Endpoints:**
- `GET  /wp-json/yoast-bridge/v1/post/{id}/meta` - read all Yoast fields
- `POST /wp-json/yoast-bridge/v1/post/{id}/meta` - write Yoast fields (JSON body)

**Setup:** WP Admin -> Users -> [testflow-bot] -> Application Passwords -> generate -> store as `WP_APP_PASSWORD_SITENAME` in `.env`.

---

## 4. Component 2: WordPress Publisher Client (Python)

### `src/testflow/models.py`

```python
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

class YoastMeta(BaseModel):
    focus_keyword: str
    meta_description: str
    seo_title: str
    canonical: Optional[HttpUrl] = None
    schema_type: str = "Article"

class AffiliateLink(BaseModel):
    anchor_text: str
    url: str
    product_name: str

class Article(BaseModel):
    title: str
    slug: str
    excerpt: str
    body_html: str
    yoast_meta: YoastMeta
    categories: list[str] = []    # Category names (resolved to WP IDs at publish time)
    tags: list[str] = []           # Tag names (resolved to WP IDs at publish time)
    featured_image_url: Optional[str] = None  # PriceRunner CDN URL - sideloaded to WP Media on publish
    affiliate_links: list[AffiliateLink] = []
    status: str = "draft"          # Always draft - human clicks publish in WP Admin

class SiteConfig(BaseModel):
    name: str         # used to look up WP_APP_PASSWORD_{NAME.upper()} in env
    url: HttpUrl
    username: str

class PublishResult(BaseModel):
    post_id: int
    post_url: str
    published_at: datetime

class ComplianceReport(BaseModel):
    passed: bool
    errors: list[str] = []
    warnings: list[str] = []
```

### `src/testflow/publisher/client.py` (key methods)

```python
import httpx
from base64 import b64encode
from testflow.models import Article, PublishResult, YoastMeta

class WordPressClient:
    def __init__(self, site_url: str, username: str, app_password: str):
        self.base = site_url.rstrip("/")
        creds = b64encode(f"{username}:{app_password}".encode()).decode()
        self._headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    def get_or_create_category(self, name: str) -> int: ...
    # GET /wp/v2/categories?search={name} - return ID if found
    # POST /wp/v2/categories {"name": name} - create and return ID if not found

    def get_or_create_tag(self, name: str) -> int: ...
    # Same pattern as categories using /wp/v2/tags

    def sideload_image(self, image_url: str, alt_text: str) -> int: ...
    # POST /wp/v2/media with source_url={image_url}
    # WP fetches the image from PriceRunner CDN and creates a local media attachment
    # Returns the media attachment ID (used as featured_media on the post)

    def create_post(self, article: Article) -> PublishResult: ...
    # POST /wp/v2/posts
    # Resolves category names -> IDs via get_or_create_category()
    # Resolves tag names -> IDs via get_or_create_tag()
    # Sideloads featured_image_url -> media ID via sideload_image()
    # Always creates with status="draft" - human publishes manually
    # Then calls set_yoast_meta() on the new post ID

    def set_yoast_meta(self, post_id: int, meta: YoastMeta) -> None: ...
    # POST /wp-json/yoast-bridge/v1/post/{id}/meta

    # NOTE: No publish_post() method - publishing is manual in WP Admin.
    # Drafts appear under Posts > Drafts. Pipeline ends when draft is created.
```

**Publish flow summary:**
1. `create_post()` - resolves categories/tags/image, POSTs as `status=draft`
2. `set_yoast_meta()` - sets focus keyword, meta description, SEO title on the draft
3. Pipeline ends - human sees draft in WP Admin, reviews, clicks Publish

**Why draft-first?** Prevents accidental live publishing of bad content. The audit gate is automated but a human sanity check is free insurance for MVP.

**Category/tag creation:** `GET /wp/v2/categories?search={name}` first - only create if not found. This makes the pipeline idempotent for repeated runs with the same category.

**Featured image sideload:** `POST /wp/v2/media` with `source_url` header. WP downloads a copy from PriceRunner CDN to the local media library. The image is then self-hosted (no ongoing dependency on PriceRunner CDN for the featured image). The first product's `image_url` is used.
```

---

## 5. Component 3: Affiliate Compliance Engine

### `affiliate/config.yaml`

```yaml
pricerunner:
  domain: "pricerunner.dk"
  ref_param: "ref-site"        # produces ?ref-site={PRICERUNNER_AFFILIATE_ID} on direct links
  widget_param: "partnerId"    # produces partnerId={PRICERUNNER_PARTNER_ID} in widget embed
  # Both credentials come from .env

disclosure:
  position: "top"   # top | bottom
  # Danish affiliate disclosure text - injected as first element inside <article> body
  # Must be present on every published article per Danish marketing law (markedsføringsloven § 6)
  html: |
    <div class="affiliate-disclosure">
      <strong>Affiliate-oplysning:</strong> Denne side indeholder affiliate-links til PriceRunner.
      Hvis du køber via vores links, modtager vi en kommission uden ekstraomkostninger for dig.
      Vores anbefalinger er baseret på produktegenskaber og brugeranmeldelser — ikke provision.
    </div>

link_rules:
  rel: "sponsored nofollow"
  target: "_blank"

# Prohibited claims - deterministic_audit() will flag any of these in the article body
# These are absolute statements that cannot be substantiated and may mislead consumers
prohibited_claims:
  - "billigst i Danmark"
  - "billigste pris"
  - "laveste pris garanteret"
  - "bedst i test"          # only allowed if a specific test source is cited
  - "nummer 1 i Danmark"
  - "markedets bedste"
  - "anbefalet af eksperter" # only allowed if specific expert/source is named
```

### Key modules

**`compliance/link_injector.py`** - scans all `<a>` tags pointing to pricerunner.dk: injects `?ref-site={PRICERUNNER_AFFILIATE_ID}` on direct product links, adds `rel="sponsored nofollow"` and `target="_blank"`.

**`compliance/disclosure.py`** - injects a Danish affiliate disclosure `<div class="affiliate-disclosure">` at the top of article body.

**`compliance/widget_injector.py`** - ensures the PriceRunner widget block is present and correctly formed.

**`compliance/rules.py`** - exports `COMPLIANCE_RULES` as a structured dict/string. This is the single source of truth for compliance criteria. It is passed verbatim into both the Generator sub-agent prompt (so it knows what to produce) and the Reviewer sub-agent prompt (so it knows what to check). Rules and Reviewer criteria are never duplicated.

**`compliance/inject_compliance.py`** - runs all deterministic transforms on an approved draft (link injection, disclosure, widget). Called by the orchestrator AFTER the Reviewer approves. Not a gate - just a transformer.

> **Note:** There is no longer a standalone `audit_article()` gate in the pipeline. The Reviewer sub-agent performs the compliance check as part of its review. Deterministic transforms (`inject_compliance`) run post-approval to enforce what the Reviewer already verified.

---

## 6. Component 4: PriceRunner Integration

The data source is PriceRunner's **unofficial internal API** (discovered via DevTools). This is category-based - products are fetched by numeric category ID, not by keyword text search. This changes the pipeline: the orchestrator must resolve the correct category ID before calling `fetch_products`.

> **Status:** Unofficial API - no auth required, standard browser headers. No guarantee of stability. Use the official PriceRunner affiliate API when/if partner API access is granted (same data, just a stable contract).

---

### Confirmed API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /dk/api/search-edge-rest/public/search/category/v4/DK/{categoryId}?size=30&sorting=POPULARITY&device=desktop` | Fetch products by category ID |
| `GET /dk/api/seo-edge-rest/public/navigation/menu/DK/hierarchy/{topicId}` | Full category tree under a topic |
| `GET /dk/api/seo-edge-rest/public/popularproducts/v3/DK/{topicId}` | Trending products across all subcategories of a topic |
| `GET /dk/api/seo-edge-rest/public/keyword/tree/DK/{topicId}` | Popular search keywords for a topic (SEO planning) |

Base URL for all: `https://www.pricerunner.dk`

Required headers: `User-Agent: <browser UA>`, `Accept: application/json`

---

### Category ID Conventions

| Prefix | Meaning | Example |
|--------|---------|---------|
| `t` | Topic (has children, not a product leaf) | `t34` = Hjem & Husholdning |
| `cl` | Leaf category (contains products) | `cl82` = Kaffemaskiner |
| `{n}-{n}` | Filter combination - **skip these** | `100003649-100015017` |

**API uses the numeric part only.** `cl82` → pass `82` to the category endpoint.

---

### `sites/pricerunner-categories.yaml` - Category ID starter set

Two-tier approach for category resolution:
- **Tier 1 (fast path):** OpenClaw looks up the product type in this YAML. Instant, works offline.
- **Tier 2 (auto-discover):** If the category is not in the YAML, OpenClaw calls `testflow_discover_categories(query)`. The tool searches PriceRunner's own category tree and returns matching IDs. OpenClaw uses the result and notes which ID to add to the YAML for next time.

```yaml
# PriceRunner category IDs (numeric part only - strip 'cl' prefix)
# Confirmed by browsing PriceRunner DK and cross-referencing API responses.
# Add new categories using: testflow_discover_categories("product type in Danish")

# Rengøring
robotstøvsugere: 1613          # Robot vacuum cleaners
støvsugere: 67                 # Traditional vacuum cleaners
robotplæneklippere: 1831       # Robot lawn mowers

# Kaffe & Te
kaffemaskiner: 82              # Coffee machines (all types)
kaffekapselmaskiner: 395       # Pod/capsule coffee machines
kaffekværne: 2035              # Coffee grinders

# Computere & Tablets
laptops: 100                   # Laptops / notebooks
tablets: 308                   # Tablets
stationære-computere: 101      # Desktop computers

# Telefoner
smartphones: 291               # Smartphones

# Lyd
trådløse-høretelefoner: 1485   # Wireless headphones
true-wireless-earbuds: 1846    # TWS earbuds / in-ears
bluetooth-højttalere: 1012     # Bluetooth speakers

# Hjem & Luft
luftrensere: 2011              # Air purifiers
luftaffugtere: 576             # Dehumidifiers
ventilatorer: 570              # Fans

# Køkken
airfryers: 2180                # Air fryers
mikrobølgeovne: 90             # Microwave ovens
brødristere: 143               # Toasters

# Personlig pleje
elektriske tandbørster: 325    # Electric toothbrushes
epilatorer: 334                # Epilators
```

> **Adding new categories:** When OpenClaw encounters an unknown product type, it calls `testflow_discover_categories("søgeord på dansk")`. The response includes category names and IDs. Add the best match to this file with a comment confirming the source.

---

### Category Discovery Tool

**`testflow_discover_categories(query: str) -> list[CategoryMatch]`**

Searches PriceRunner's category tree for categories matching the query string. Called by OpenClaw when a product type is not in `pricerunner-categories.yaml`.

```python
# In src/testflow/content/pricerunner.py - add to PriceRunnerClient

def discover_categories(self, query: str) -> list[dict]:
    """
    Search PriceRunner's category tree for categories matching a query.
    Returns list of {name, id, parent_name, url} dicts sorted by relevance.
    Uses the navigation/menu API with the top-level topic tree.
    """
    # Fetch root topic tree (topic t1 = everything)
    url = f"{self.BASE_SEO}/public/navigation/menu/DK/hierarchy/1"
    data = self._get(url)

    query_lower = query.lower()
    matches = []

    def walk(node, parent_name=""):
        name = node.get("name", "")
        node_id = node.get("id", "")
        # Strip 'cl' or 't' prefix for the numeric ID
        numeric_id = node_id.lstrip("clt")
        if query_lower in name.lower() and numeric_id.isdigit():
            matches.append({
                "name": name,
                "id": int(numeric_id),
                "parent": parent_name,
                "raw_id": node_id,
            })
        for child in node.get("children", []):
            walk(child, parent_name=name)

    for top_node in data.get("children", []):
        walk(top_node)

    return sorted(matches, key=lambda m: len(m["name"]))  # shorter name = more specific
```

**Tool server endpoint** (`tool_server.py`):
```python
@app.post("/tools/discover_categories")
async def discover_categories(body: dict):
    query = body.get("query", "")
    client = PriceRunnerClient()
    return {"categories": client.discover_categories(query)}
```

**TypeScript plugin registration** (`openclaw-plugin-testflow/src/index.ts`) - add alongside the other tools:
```typescript
{
  name: "testflow_discover_categories",
  description: "Search PriceRunner's category tree for a product type. Returns category names and numeric IDs. Call this when a product category is not in pricerunner-categories.yaml.",
  inputSchema: Type.Object({
    query: Type.String({ description: "Product type to search for, in Danish (e.g. 'robotstøvsugere', 'kaffemaskiner')" }),
  }),
  handler: async (input) => client.post("/tools/discover_categories", input),
},
```

**Skill doc update** - change step 4 in "Resolution steps" from:
> "If the category is not in the file, tell the user..."

To:
> "If the category is not in `pricerunner-categories.yaml`, call `testflow_discover_categories(query)` with the Danish product type name. Use the returned ID. Note which ID to add to the YAML for next time."

---

### `PRProduct` data model (`src/testflow/models.py`)

```python
import os
from pydantic import BaseModel
from typing import Optional

class PRProduct(BaseModel):
    id: str
    name: str
    price_min: float          # lowest merchant price in DKK
    price_max: float          # highest merchant price in DKK
    url: str                  # absolute pricerunner.dk product URL
    image_url: str            # CDN image URL (hotlinked in MVP)
    rating: Optional[float]   # 0-5 star rating, if available
    review_count: Optional[int]
    merchant_count: int       # number of merchants selling this product
    category_id: int
    category_name: str

    @property
    def affiliate_url(self) -> str:
        """Direct affiliate link - appends ref-site param."""
        ref = os.getenv("PRICERUNNER_AFFILIATE_ID", "")
        return f"{self.url}?ref-site={ref}"

    @property
    def price_display(self) -> str:
        """Human-readable price for article body (Danish format)."""
        return f"Fra {self.price_min:.0f} kr"
```

---

### `PriceRunnerClient` (`src/testflow/content/pricerunner.py`)

```python
import time, json, random, httpx
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from testflow.models import PRProduct

CACHE_DIR = Path("cache/pricerunner")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Rotate through realistic browser UAs on every request.
# This prevents a single fingerprint from triggering bot detection.
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def _is_retryable(exc: Exception) -> bool:
    """Retry on 429 (rate limited), 503 (overloaded), or timeout."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in {429, 503}
    ) or isinstance(exc, httpx.TimeoutException)

class PriceRunnerClient:
    BASE_SEARCH    = "https://www.pricerunner.dk/dk/api/search-edge-rest"
    BASE_SEO       = "https://www.pricerunner.dk/dk/api/seo-edge-rest"
    RATE_LIMIT_SEC = 1.5   # base delay between requests (seconds)
    JITTER_MAX     = 0.8   # max additional random jitter (seconds)

    def __init__(self):
        self._last_request = 0.0
        # No default headers on the session - rotated per-request in _get_headers()
        self._session = httpx.Client(timeout=15)

    def _get_headers(self) -> dict:
        """Build realistic browser headers with a randomly chosen User-Agent."""
        return {
            "User-Agent": random.choice(UA_POOL),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.pricerunner.dk/",
            "Origin": "https://www.pricerunner.dk",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=3, max=30),  # 3s → 6s → 12s → 24s → 30s cap
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, url: str, params: dict = None) -> dict:
        """Rate-limited GET with jitter and exponential backoff on 429/503/timeout."""
        # Rate limit: base delay + random jitter to avoid predictable request patterns
        elapsed = time.time() - self._last_request
        wait = self.RATE_LIMIT_SEC + random.uniform(0.0, self.JITTER_MAX)
        if elapsed < wait:
            time.sleep(wait - elapsed)
        resp = self._session.get(url, params=params, headers=self._get_headers())
        self._last_request = time.time()
        resp.raise_for_status()   # raises HTTPStatusError → triggers retry on 429/503
        return resp.json()

    def fetch_products_by_category(self, category_id: int, limit: int = 10,
                                   sorting: str = "POPULARITY") -> list[PRProduct]:
        """Main product fetch. Returns up to `limit` products sorted by POPULARITY."""
        cache_path = CACHE_DIR / f"products-{category_id}.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 86400:  # 24h cache
            raw = json.loads(cache_path.read_text())
        else:
            url = f"{self.BASE_SEARCH}/public/search/category/v4/DK/{category_id}"
            raw = self._get(url, {"size": limit, "sorting": sorting, "device": "desktop"})
            cache_path.write_text(json.dumps(raw))
        return self._parse_products(raw, category_id)

    def fetch_category_tree(self, topic_id: str) -> dict:
        """Full category tree under a topic. Cached for 30 days (essentially static)."""
        cache_path = CACHE_DIR / f"tree-{topic_id}.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 2_592_000:  # 30 days
            return json.loads(cache_path.read_text())
        url = f"{self.BASE_SEO}/public/navigation/menu/DK/hierarchy/{topic_id}"
        data = self._get(url)
        cache_path.write_text(json.dumps(data))
        return data

    def fetch_popular_products(self, topic_id: str) -> list[PRProduct]:
        """~15 trending products across all subcategories of a topic. 6h cache."""
        cache_path = CACHE_DIR / f"popular-{topic_id}.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 21600:  # 6h
            raw = json.loads(cache_path.read_text())
        else:
            url = f"{self.BASE_SEO}/public/popularproducts/v3/DK/{topic_id}"
            raw = self._get(url)
            cache_path.write_text(json.dumps(raw))
        return self._parse_products(raw, category_id=None)

    def fetch_keyword_tree(self, topic_id: str) -> list[dict]:
        """~50 popular search keywords for a topic. Useful for SEO/content planning."""
        url = f"{self.BASE_SEO}/public/keyword/tree/DK/{topic_id}"
        return self._get(url)  # lightweight, not cached

    def _parse_products(self, raw: dict, category_id: int | None) -> list[PRProduct]:
        """Parse API response into PRProduct list. Field names confirmed from DevTools."""
        # NOTE: exact field names must be confirmed on first real API call.
        # Adjust keys here if the response shape differs.
        results = []
        for item in raw.get("products", raw.get("items", [])):
            try:
                results.append(PRProduct(
                    id=str(item["id"]),
                    name=item["name"],
                    price_min=item.get("minPrice", {}).get("amount", 0),
                    price_max=item.get("maxPrice", {}).get("amount", 0),
                    url="https://www.pricerunner.dk" + item.get("url", ""),
                    image_url=item.get("imageUrl", ""),
                    rating=item.get("rating"),
                    review_count=item.get("reviewCount"),
                    merchant_count=item.get("merchantCount", 0),
                    category_id=category_id or 0,
                    category_name=item.get("categoryName", ""),
                ))
            except Exception as e:
                # Log and skip malformed products rather than crashing the pipeline
                pass
        return results
```

> **Field name caveat:** `_parse_products` uses assumed field names based on typical PriceRunner API shapes. The exact keys (`minPrice.amount`, `imageUrl`, etc.) must be verified on the first real API call and adjusted as needed.

---

### Category ID Mapping (`sites/pricerunner-categories.yaml`)

The orchestrator cannot discover category IDs from user intent alone - it needs a lookup table. This YAML is the mapping. The orchestrator's skill document references it.

```yaml
# sites/pricerunner-categories.yaml
# Numeric ID = the category ID passed to fetch_products_by_category()
# Add entries here as new article topics are added.

categories:
  # Køkkenapparater (under t14)
  kaffemaskiner: 82
  blendere: 84
  vandkedler: 68
  airfryer: 81
  frituregyder: 81       # same category as airfryer
  brødristere: 69
  stavblendere: 85
  røremaskiner: 1244
  vandkogere: 68
  ismaskiner: 250

  # Hvidevarer (under t3)
  robotstøvsugere: 1613
  støvsugere: 19
  vaskemaskiner: 14
  tørretumblere: 17
  opvaskemaskiner: 13
  mikrobølgeovne: 3

  # Have & Udemiljø (under t1424)
  robotplæneklippere: 1595
  grill: 335
  plæneklippere: 119
  højtryksrensere: 638

  # Hus (under t1426)
  strygejern: 80
  luftrensere: 453
  ventilatorer: 401
```

**Adding new categories:** Look up the `cl` ID in the PriceRunner navigation tree, strip the `cl` prefix, add a row here.

---

### Affiliate Link and Widget Design

**Direct affiliate links (per product):**
```
{product.url}?ref-site={PRICERUNNER_AFFILIATE_ID}
```
Example: `https://www.pricerunner.dk/pl/82-kaffemaskiner/...?ref-site=myid`

Generated automatically by `PRProduct.affiliate_url` property. The compliance engine enforces `rel="sponsored nofollow"` on all these links.

**PriceRunner JS widget (per-category comparison block):**
```html
<!-- Inserted by widget_injector.py into article body -->
<div class="pr-widget" data-category-id="{categoryId}"></div>
<script src="https://partner.pricerunner.dk/api/widget/v2/category/{categoryId}?partnerId={PRICERUNNER_PARTNER_ID}&locale=da-DK" async></script>
```

> **Note:** Exact widget embed syntax must be confirmed from PriceRunner partner documentation on first implementation. The `partnerId` is separate from the `ref-site` affiliate ID.

**Two env vars needed:**
- `PRICERUNNER_AFFILIATE_ID` - for `?ref-site=` query param on direct links
- `PRICERUNNER_PARTNER_ID` - for `partnerId=` in the widget embed

---

### Explicit Product Filtering (for `versus` / `single-review`)

When the user specifies exact product names (e.g. "compare Roomba j9+ vs Ecovacs Deebot X2"), the pipeline:
1. Fetches all products for the relevant category (category_id still required)
2. Filters by fuzzy name match against `explicit_products` list
3. If fewer than required products are found → abort with clear error

```python
def filter_by_explicit(products: list[PRProduct], explicit: list[str]) -> list[PRProduct]:
    """Case-insensitive substring match. Returns products matching any explicit name."""
    matched = []
    for product in products:
        if any(ep.lower() in product.name.lower() for ep in explicit):
            matched.append(product)
    return matched
```

If 0 matches: abort. If partial match (e.g. 1 of 2 requested): log warning, continue with what was found.

---

### Cache Directory

```
cache/
└── pricerunner/
    ├── products-82.json        # 24h TTL
    ├── products-1613.json
    ├── tree-t34.json           # 30d TTL
    ├── popular-t34.json        # 6h TTL
    └── ...
```

`cache/` is gitignored (add to `.gitignore`).

---

> **`src/testflow/content/generator.py` - REMOVED**
> This file existed in an earlier architecture where Python called Claude API directly. In the current design, **OpenClaw IS the article generator** - it handles all reasoning (brief, article, review, SEO, CRO) in its own session using its own intelligence. Python makes zero LLM calls. `generator.py` has no role and is not created.

---

## 7. Orchestration Tools & Runner

**The key design:** OpenClaw IS the orchestrator. It reads the skill document, does all reasoning (brief, article, review, SEO, CRO), and calls the Python tools for deterministic operations. The Python layer contains NO LLM calls.

### How OpenClaw calls Python tools

`tool_server.py` runs a FastAPI server on `localhost:8000`. OpenClaw is configured to call these HTTP endpoints as tools. OpenClaw passes JSON in, gets JSON back. No SDK, no API keys, no sub-agent framework needed.

```
OpenClaw → POST http://localhost:8000/tools/fetch_products_by_category
         ← { "products": [...] }

OpenClaw → POST http://localhost:8000/tools/inject_compliance
         ← { "html": "...", "transforms_applied": 5 }

OpenClaw → POST http://localhost:8000/tools/create_draft
         ← { "post_id": 123, "post_url": "https://..." }
```

The skill document tells OpenClaw what endpoints exist and what parameters each takes.

### Python tools (`src/testflow/orchestration/tools.py`)

These are the only functions OpenClaw calls. None of them call an LLM.

```python
# Data fetching (PriceRunner API + local cache)
fetch_products_by_category(category_id: int, limit: int = 10) -> list[PRProduct]
filter_by_explicit(products: list[PRProduct], explicit: list[str]) -> list[PRProduct]

# Compliance transforms (deterministic - run after article is approved)
inject_compliance(html: str, affiliate_id: str, partner_id: str) -> str
# adds ?ref-site= on all pricerunner.dk links, disclosure div at top, widget embed

# Safety audit (deterministic rule checks)
deterministic_audit(html: str) -> ComplianceReport
# checks disclosure present, ref-site on all links, no prohibited claims

# Publishing (WP REST API - creates draft, never publishes live)
create_draft(article: Article, site_config: SiteConfig) -> PublishResult

# State (SQLite)
record_run(run_id, topic, keyword, category_id, article_type, status, stats) -> None
record_review_attempt(run_id, phase, passed, score, feedback) -> None
get_published_count(site_name: str, since_days: int = 7) -> int
get_published_titles(site_name: str) -> list[str]   # for internal linking context

# Ideas (OpenClaw uses PriceRunner keyword tree, not this - but available for CLI use)
get_keyword_ideas(seed_keyword: str, n: int = 5) -> list[dict]
```

### OpenClaw context builders (`src/testflow/orchestration/prompts.py`)

One function per reasoning phase. Each returns a structured string that OpenClaw reads to understand its task for that phase. OpenClaw produces the output from this context using its own reasoning.

```python
def build_brief_context(topic, keyword, products, template, site_rules, feedback=None) -> str: ...
def build_brief_review_context(brief, template) -> str: ...
def build_article_context(brief, products, template, compliance_rules, feedback=None) -> str: ...
def build_article_review_context(draft, brief, template, compliance_rules) -> str: ...
def build_seo_context(draft, keyword, related_keywords, published_titles) -> str: ...
def build_cro_context(draft, template) -> str: ...
def build_optimization_review_context(draft, original_approval_score) -> str: ...
```

> These are used by `pipeline.py` when a human triggers the pipeline via CLI (`runner.py`). When OpenClaw drives the pipeline itself, it builds its own context from the skill document instructions. `prompts.py` is the canonical definition of what each phase should contain.

### Orchestrator Skill document (`skills/affiliate-pipeline.md`)

This skill document lives in OpenClaw's skill folder. It is the **complete instruction set for OpenClaw** - it teaches OpenClaw how to:
1. Map any user request to structured pipeline parameters (Mode A / Mode B)
2. Call the correct Python tools via the tool server in the correct order
3. Switch between reasoning phases (brief, article, SEO, CRO, review)
4. Handle retries and abort conditions

This is where all orchestration logic lives. The Python pipeline is the fallback for CLI use only.

```markdown
# Affiliate Article Pipeline Skill

## Available tool
`run_article_pipeline(article_type, topic, keyword, category_id, explicit_products, site)`

## Two input modes

### Mode A — Product-first (user gives product name(s))
The user gives you one or more specific product names. You resolve everything else.

**Article type rules - YOU decide based on product count AND intent signals:**

| Products given | Signals to look for | Template |
|---|---|---|
| 1 | (always) | `single-review` |
| 2 | "vs", "versus", "mod", "eller", "bedst" | `versus` |
| 2 | "sammenlign", "forskel", "difference", no clear signal | `comparison` |
| 3+ | user asked for "de bedste X", "top X", "anbefalinger" | `best-of-list` |
| 3+ | user named specific products, no ranking intent | `comparison` |

**IMPORTANT:** You decide the template. The Brief Generator only writes content - it never changes the template you chose.

**Resolution steps:**
1. Count products and read intent signals → pick template from the table above
2. Identify the product category using your knowledge (e.g. "Roomba j9+" → robot vacuum → robotstøvsugere)
3. Look up the category ID in `sites/pricerunner-categories.yaml`
4. If the category is not in `sites/pricerunner-categories.yaml`, call `testflow_discover_categories(query)` with the Danish product type name (e.g. `"robotstøvsugere"`). Use the best matching ID from the result. Note to the user which entry to add to the YAML for next time.
5. Generate a natural Danish `topic` and `keyword` based on the product(s) and chosen template
6. Set `explicit_products` to the full list of product names the user gave

**Product-first examples:**
| User says | Resolved call |
|---|---|
| `"Roomba j9+"` | `article_type="single-review", topic="Roomba j9+ anmeldelse - er den pengene værd?", keyword="roomba j9+ anmeldelse", category_id=1613, explicit_products=["Roomba j9+"]` |
| `"Roomba j9+ vs Ecovacs Deebot X2"` | `article_type="versus", topic="Roomba j9+ vs Ecovacs Deebot X2 - hvem vinder?", keyword="roomba j9+ vs ecovacs deebot x2", category_id=1613, explicit_products=["Roomba j9+","Ecovacs Deebot X2"]` |
| `"sammenlign Roomba j9+ og Ecovacs Deebot X2"` | `article_type="comparison", topic="Roomba j9+ eller Ecovacs Deebot X2 - en grundig sammenligning", keyword="roomba j9+ vs ecovacs deebot x2", category_id=1613, explicit_products=["Roomba j9+","Ecovacs Deebot X2"]` |
| `"DeLonghi Magnifica", "Jura E8", "Siemens EQ.9"` | `article_type="comparison", topic="DeLonghi Magnifica vs Jura E8 vs Siemens EQ.9", keyword="bedste kaffemaskine test", category_id=82, explicit_products=["DeLonghi Magnifica","Jura E8","Siemens EQ.9"]` |

---

### Mode B — Intent-first (user describes what they want)
The user gives a natural language request about a category or topic. You resolve the article type and category from the description.

**Article type from intent:**
| Type | When to use |
|---|---|
| `best-of-list` | User wants a ranked list for a category ("de bedste X") |
| `buying-guide` | User wants purchase advice ("hvordan vælger jeg X", "guide til X") |
| `single-review` | User asks to review one specific product |
| `versus` | User wants to compare exactly 2 specific products |
| `comparison` | User wants to compare 3+ specific products |

**Intent-first examples:**
| User says | Resolved call |
|---|---|
| "skriv om de bedste robotstøvsugere" | `article_type="best-of-list", topic="Bedste robotstøvsugere 2025", keyword="bedste robotstøvsuger", category_id=1613, explicit_products=[]` |
| "lav en indkøbsguide til kaffemaskiner" | `article_type="buying-guide", topic="Sådan vælger du kaffemaskine", keyword="kaffemaskine guide", category_id=82, explicit_products=[]` |

---

## Parameter resolution rules (both modes)
- `topic`: a natural, clickable Danish article title
- `keyword`: primary SEO keyword in Danish (what a user would Google)
- `category_id`: numeric PriceRunner category ID from `sites/pricerunner-categories.yaml`
- `explicit_products`: always populate when the user named specific products; empty list for category-level articles
- `site`: default to `"sites/site-one.yaml"` unless the user specifies otherwise

## Category ID lookup
Open `sites/pricerunner-categories.yaml`. Match the product type to a key. Use the numeric value.
If the key is missing, tell the user — do not guess or make up a category ID.

---

## Pipeline execution (after resolving params)

You are the orchestrator. You run all reasoning inline in your session. You call the `testflow_*` tools for deterministic operations. Sub-agents are not used in MVP.

**Available tools:** `testflow_fetch_products`, `testflow_inject_compliance`, `testflow_deterministic_audit`, `testflow_create_draft`, `testflow_record_run`, `testflow_published_titles`

> If these tools are not in your tool list, the TestFlow plugin is not loaded. Tell the user to run `openclaw plugins install ./openclaw-plugin-testflow` and restart OpenClaw.

### Step 0 - Fetch products
```
testflow_fetch_products(category_id=<id>, limit=10, explicit_products=[...])
→ { "products": [ { "name", "price_min", "affiliate_url", "image_url", "rating" } ] }
```
If 0 products returned, tell the user and stop.

### Step 1 - Brief loop (max 2 attempts)
Reason inline. Produce a `ContentBrief` JSON object:
```json
{
  "topic": "...",
  "keyword": "...",
  "article_type": "...",
  "target_word_count": 1200,
  "key_angles": ["...", "..."],
  "product_order": ["Product A", "Product B"],
  "recommended_cta_positions": ["after_intro", "after_verdict"],
  "outline": ["## Section 1", "## Section 2"]
}
```
Then review it inline as the Brief Reviewer. Apply these criteria:
- Is the topic clear and clickable in Danish?
- Does the outline match the template structure?
- Are there at least 3 distinct angles (not generic filler)?

If score < 7/10: note specific issues and repeat the Brief phase with that feedback. After 2 failed attempts, tell the user and stop.

### Step 2 - Article loop (max 3 attempts)
Reason inline. Write the full article HTML following the brief and template. The article must:
- Match the template structure exactly (sections in order)
- Include `<div class="affiliate-disclosure">` as the very first element
- All PriceRunner links must use `affiliate_url` from the product data (already has `?ref-site=` appended)
- Include `rel="sponsored nofollow"` and `target="_blank"` on all PriceRunner links
- Do NOT include prohibited claims: "billigste pris garanteret", "laveste pris", "garanti for", "vi garanterer"
- Include the PriceRunner widget placeholder `<div class="pr-widget" data-category="<category_id>"></div>`
- Produce `yoast_meta`: `{ focus_keyword, seo_title, meta_description }`

Produce an `ArticleDraft` JSON object:
```json
{
  "title": "...",
  "slug": "...",
  "body_html": "...",
  "yoast_meta": { "focus_keyword": "...", "seo_title": "...", "meta_description": "..." },
  "categories": ["Kategori"],
  "tags": ["tag1", "tag2"],
  "featured_image_url": "https://cdn.pricerunner.dk/..."
}
```
Then review inline as the Article Reviewer:
- Disclosure present as first element? (hard fail if missing)
- All PriceRunner links have `?ref-site=` + `rel="sponsored nofollow"` + `target="_blank"`? (hard fail if any missing)
- Score the article structure, Danish language quality, completeness (0-10)

If score < 7/10 or hard fail: note specific issues and retry. After 3 failed attempts, tell the user and stop.

### Step 3 - SEO + CRO pass (max 1 retry)
Reason inline.

**SEO pass:** Update heading structure (H1 → H2 → H3 hierarchy), ensure primary keyword appears naturally in H1, intro paragraph, and at least 2 subheadings. Add 2-3 internal links to existing articles (call `testflow_published_titles(site_name="site_one")` to get titles).

**CRO pass:** Review CTA placement against the template's `recommended_cta_positions`. Ensure the product with the best value is prominently positioned. Verify at least 1 CTA per 400 words.

Then review inline as the Optimization Reviewer:
- Is keyword stuffed? (fail if keyword appears > 1.5% of word count)
- Are headings logical and keyword-rich without being spammy?
- Are CTAs well-placed?

If failed: retry SEO+CRO once with specific issues noted. After 2 total attempts, tell the user this article needs human review and stop (do NOT publish).

### Step 4 - Deterministic compliance
```
testflow_inject_compliance(html=<body_html>, affiliate_id=<from env>, partner_id=<from env>)
→ { "html": "...", "transforms_applied": N }

testflow_deterministic_audit(html=<result html>)
→ { "passed": true|false, "errors": [...], "warnings": [...] }
```
If `passed: false`: log errors, tell the user and stop. Do NOT call `testflow_create_draft`.

### Step 5 - Publish draft
```
testflow_create_draft(article={...ArticleDraft with updated body_html...}, site="sites/site-one.yaml")
→ { "post_id": 123, "post_url": "https://..." }
```
> **Note:** `testflow_create_draft` will pause and ask for your approval before making any WordPress API call. Approve or deny in the chat. Timeout (5 min) → auto-deny.

```
testflow_record_run(run_id=<uuid>, topic=..., keyword=..., category_id=N, article_type=..., status="success")
```

Tell the user: "Draft created: <post_url> - open WP Admin to review and publish."

---

## What you must never do
- Guess a category ID. Always read it from `pricerunner-categories.yaml`.
- Publish directly. All articles go as WP drafts. The human publishes manually.
- Skip the deterministic audit. Even if the article looks clean, always call the audit endpoint.
- Make up product URLs. Always use `affiliate_url` from the fetched product data.
```

The pipeline is a **dumb execution engine** - it receives structured params and runs. The orchestrator's intelligence (guided by this skill) handles all intent interpretation before calling the pipeline.

---

### Full sequential pipeline (`src/testflow/orchestration/pipeline.py`)

```python
BRIEF_MAX_RETRIES    = 2
ARTICLE_MAX_RETRIES  = 3
PASS_SCORE           = 7   # out of 10

def run_article_pipeline(
    article_type: str,
    topic: str,
    keyword: str,
    category_id: int,           # PriceRunner numeric category ID (from pricerunner-categories.yaml)
    explicit_products: list[str],
    site_config: SiteConfig
) -> PublishResult | None:

    client = PriceRunnerClient()
    products = client.fetch_products_by_category(category_id, limit=10)

    if explicit_products:
        # For versus/single-review: filter to only the products the user named
        products = filter_by_explicit(products, explicit_products)

    if not products:
        log(f"No products found for category {category_id} (keyword: '{keyword}'). Aborting.")
        return None

    template = load_template(article_type)
    run_id = generate_run_id()  # UUID for correlating all logs/DB entries in this pipeline run

    # --- STAGE 1: Brief loop ---
    # NOTE: This pipeline.py is for human CLI use. When OpenClaw drives the pipeline,
    # it handles the loop logic itself based on the skill document instructions.
    # The context strings below are what OpenClaw reads for each phase.
    brief = None
    feedback = None
    for attempt in range(1, BRIEF_MAX_RETRIES + 1):
        # OpenClaw reads this context and produces ContentBrief JSON
        context = build_brief_context(topic, keyword, products, template, site_config.rules, feedback)
        # [OpenClaw reasons here → returns ContentBrief JSON]
        brief = openclaw_phase(context)   # see note below

        review_context = build_brief_review_context(brief, template)
        review = openclaw_phase(review_context)   # returns ReviewReport JSON

        record_review_attempt(run_id, "brief", review.passed, review.score, review.feedback)
        if review.passed and review.score >= PASS_SCORE:
            break
        feedback = review.feedback
        if attempt == BRIEF_MAX_RETRIES:
            log(f"Brief for '{topic}' failed after {BRIEF_MAX_RETRIES} attempts. Aborting.")
            return None

    # --- STAGE 2: Article loop ---
    draft = None
    feedback = None
    for attempt in range(1, ARTICLE_MAX_RETRIES + 1):
        context = build_article_context(brief, products, template, COMPLIANCE_RULES, feedback)
        draft   = openclaw_phase(context)

        review_context = build_article_review_context(draft, brief, template, COMPLIANCE_RULES)
        review = openclaw_phase(review_context)

        record_review_attempt(run_id, "article", review.passed, review.score, review.feedback)
        if review.passed and review.score >= PASS_SCORE:
            article_approval_score = review.score
            break
        feedback = review.feedback
        if attempt == ARTICLE_MAX_RETRIES:
            log(f"Article '{topic}' failed after {ARTICLE_MAX_RETRIES} attempts. Aborting.")
            return None

    # --- STAGES 3-4: Optimization loop (SEO → CRO → Review, max 1 retry) ---
    OPT_MAX_RETRIES = 1
    opt_issues = None
    published_titles = get_published_titles(site_config.name)
    for opt_attempt in range(1, OPT_MAX_RETRIES + 2):
        draft = openclaw_phase(build_seo_context(draft, keyword, [], published_titles, opt_issues))
        draft = openclaw_phase(build_cro_context(draft, template, opt_issues))

        opt_review = openclaw_phase(build_optimization_review_context(draft, article_approval_score))
        record_review_attempt(run_id, "optimization", opt_review.passed, opt_review.score, opt_review.feedback)

        if opt_review.passed:
            break
        if opt_attempt > OPT_MAX_RETRIES:
            log(f"Optimization review failed for '{topic}'. Flagging for human review.")
            return None
        opt_issues = opt_review.issues

    # --- STAGE 5: Deterministic compliance + safety audit ---
    html    = inject_compliance(draft.body_html, AFFILIATE_ID, PARTNER_ID)
    audit   = deterministic_audit(html)
    if not audit.passed:
        log(f"Deterministic audit failed: {audit.errors}")
        return None
    draft.body_html = html

    # --- STAGE 6: Create draft in WordPress ---
    result = create_draft(draft, site_config)
    record_run(run_id, topic, keyword, category_id, article_type, "success", stats)
    log(f"Draft created: {result.post_url} - open WP Admin to review and publish.")
    return result
```

> **`openclaw_phase(context)`** is a placeholder representing "OpenClaw reads this context string and produces JSON". In the CLI context, this could be a direct API call if needed for testing. In production, OpenClaw drives this itself without any Python calling an LLM - OpenClaw IS the one calling these Python functions and doing the reasoning between calls.

### `runner.py` - CLI entry point

Two input modes match the orchestrator skill document:

**Mode A - Product-first (orchestrator resolves article type, topic, keyword, category from intent signals):**
```
# Single product → always single-review
python runner.py --site sites/site-one.yaml --products "Roomba j9+"

# Two products + "vs" signal → versus (battle format)
python runner.py --site sites/site-one.yaml --products "Roomba j9+ vs Ecovacs Deebot X2"

# Two products + neutral signal → comparison (balanced)
python runner.py --site sites/site-one.yaml --products "sammenlign Roomba j9+ og Ecovacs Deebot X2"

# Three+ named products → comparison
python runner.py --site sites/site-one.yaml --products "DeLonghi Magnifica" "Jura E8" "Siemens EQ.9"
```

**Mode B - Intent-first (all params explicit):**
```
python runner.py --site sites/site-one.yaml --topic "Bedste robotstøvsugere 2026" --keyword "bedste robotstøvsuger" --template best-of-list --category 1613
python runner.py --site sites/site-one.yaml --topic "Sådan vælger du kaffemaskine" --keyword "kaffemaskine guide" --template buying-guide --category 82
```

**Other usage:**
```
python runner.py --site sites/site-one.yaml --ideas --seed "kaffemaskiner"   # keyword ideation only
python runner.py --site sites/site-one.yaml --products "Roomba j9+" --dry-run
```

> **Note:** `runner.py` is a human-facing CLI helper. In normal operation, you talk to OpenClaw and it calls the tool server directly. `runner.py` is useful for manual testing without OpenClaw running.

**CLI flags:**
- `--site` (required): path to site YAML config
- `--products` (Mode A): one or more product names (or a natural language string with products embedded); article type inferred from count + intent signals (1=review always; 2=versus or comparison; 3+=comparison or best-of-list)
- `--topic` (Mode B): Danish article title
- `--keyword` (Mode B): primary SEO keyword
- `--template` (Mode B): article type (best-of-list, single-review, comparison, buying-guide, versus)
- `--category` (Mode B): numeric PriceRunner category ID from `sites/pricerunner-categories.yaml`
- `--dry-run` (optional): full pipeline but skip the final `create_draft` call
- `--ideas` + `--seed` (optional): keyword ideation using PriceRunner keyword tree

**Mode B flow in `runner.py` (all params explicit - simplest path):**
```python
result = run_article_pipeline(
    article_type=args.template, topic=args.topic, keyword=args.keyword,
    category_id=args.category, explicit_products=[], site_config=site_config
)
```

**Mode A flow:** Pass `--products` to OpenClaw (or resolve manually with the categories YAML and call Mode B directly).

Full pipeline: fetch → brief loop → article loop → optimization loop → compliance → audit → create draft → record

---

## 8. Configuration Design

### `.env` (gitignored)
```
# PriceRunner - two separate credentials
PRICERUNNER_AFFILIATE_ID=your_ref_site_id    # appended as ?ref-site=XXX on direct product links
PRICERUNNER_PARTNER_ID=your_partner_id       # used as partnerId=XXX in JS widget embed

# WordPress - one app password per site
WP_APP_PASSWORD_SITE_ONE=xxxx xxxx xxxx xxxx xxxx xxxx
WP_APP_PASSWORD_SITE_TWO=xxxx xxxx xxxx xxxx xxxx xxxx

# Tool server
TOOL_SERVER_HOST=localhost
TOOL_SERVER_PORT=8000
```

**No `ANTHROPIC_API_KEY` or `TESTFLOW_RUNTIME` needed.** OpenClaw provides the LLM - no external API calls from Python. The tool server is called by OpenClaw, not by the Python code making outbound LLM requests.

### `sites/site-one.yaml` (primary test site)
```yaml
name: site_one
url: https://www.site-one.dk
username: testflow-bot
```

### `sites/site-two.yaml` (ready, not used in MVP testing)
```yaml
name: site_two
url: https://www.site-two.dk
username: testflow-bot
```

Env var naming rule: `WP_APP_PASSWORD_{name.upper()}` (e.g. `WP_APP_PASSWORD_SITE_ONE`)

**Multi-site design:** The codebase is multi-site from day one. `runner.py` accepts `--site <path>` pointing to any site YAML. The pipeline has no hardcoded site assumptions. Running against a second site is simply passing a different `--site` argument. Testing in MVP uses only `site-one.yaml`.

---

### How the orchestrator gets its instructions

In MVP, a human (you) gives the orchestrator a free-text instruction. The orchestrator reads its skill document and resolves structured pipeline parameters natively - no sub-agent needed. No queue, no scheduler.

**Instruction patterns the orchestrator handles (via skill document):**

| Your instruction | Article type resolved |
|---|---|
| "do a review of product X" | `single-review` |
| "compare product A vs product B" | `versus` |
| "create a comparison of A, B and C" | `comparison` |
| "write a best-of article about robot vacuums" | `best-of-list` |
| "create a buying guide for air purifiers" | `buying-guide` |
| "write something about robot vacuums under 2000kr" | `best-of-list` + price filter hint |

**Scheduling is Phase 2.** Until the pipeline reliably produces quality content, you trigger it manually. Autonomous scheduling only makes sense once output quality is validated.

---

## 8b. OpenClaw agent configuration

OpenClaw needs to know which tool profile to use and how sub-agents should behave. This goes in your OpenClaw `config.json5` (or equivalent config file):

```json5
{
  agents: {
    defaults: {
      subagents: {
        // MVP: "suggest" (default). Phase 2: change to "prefer" to encourage
        // OpenClaw to delegate article generation to isolated sub-agents.
        delegationMode: "suggest",
        maxConcurrent: 4,
        // Phase 2: set maxSpawnDepth: 2 to enable orchestrator → worker sub-agents
        // maxSpawnDepth: 1,  // default - sub-agents cannot spawn children
      },
    },
  },
  tools: {
    // "coding" profile includes sessions_spawn, sessions_yield, web_fetch, exec, process, read, etc.
    // This is required for OpenClaw to make HTTP calls to the tool server.
    profile: "coding",
  },
}
```

**Why `coding` profile?** The `coding` profile gives OpenClaw `web_fetch` and `exec` tools (needed to call `http://localhost:8000` tool server endpoints), plus `sessions_spawn` and `sessions_yield` for optional Phase 2 sub-agent delegation.

**Phase 2 sub-agent pattern (not for MVP):**
When context grows too large during article generation, delegate expensive phases via:
```
sessions_spawn({
  task: "Generate a single-review article draft based on the brief: <ContentBrief JSON>",
  context: "fork",   // child gets current transcript including products + brief
  taskName: "article_writer",
  runTimeoutSeconds: 300
})
sessions_yield()   // end current turn, wait for child to announce result
```
Sub-agents automatically receive `AGENTS.md` (injected by OpenClaw), giving them the tool server URL and key file paths. They can call the tool server directly.

---

## 9. `pyproject.toml` dependencies

```toml
[tool.poetry.dependencies]
python = "^3.11"
httpx = "^0.27"          # HTTP client for PriceRunner API + WP REST API
pydantic = "^2.7"        # Data models and validation throughout
fastapi = "^0.111"       # tool_server.py - exposes Python tools to OpenClaw via HTTP
uvicorn = "^0.30"        # ASGI server for tool_server.py
beautifulsoup4 = "^4.12" # HTML parsing for compliance engine
lxml = "^5.0"            # Faster HTML parser for BeautifulSoup4 (bs4 falls back to html.parser without it)
python-dotenv = "^1.0"   # .env loading
pyyaml = "^6.0"          # Site configs, template files, affiliate config
tenacity = "^8.3"        # Retry logic for HTTP calls (PriceRunner API, WP REST)

[tool.poetry.dev-dependencies]
pytest = "^8.0"
pytest-httpx = "^0.30"   # Mock httpx requests in tests (WP REST + PriceRunner API)
ruff = "^0.4"
mypy = "^1.10"
```

**Not in dependencies (built-in Python):** `sqlite3`, `pathlib`, `uuid`, `json`, `logging`, `datetime`

**Removed:** `anthropic` (no LLM API calls from Python). OpenClaw provides the LLM.

**Not included (Phase 2+):** `schedule` or `APScheduler` for cron-style scheduling; `aiofiles` for async file I/O (not needed at MVP scale).

---

## 9b. `tool_server.py` - FastAPI HTTP tool server

OpenClaw calls Python tools via HTTP. This server runs locally alongside OpenClaw. Start it before starting OpenClaw:

```bash
uvicorn tool_server:app --host localhost --port 8000
```

**Endpoints exposed to OpenClaw:**

```python
from fastapi import FastAPI
from testflow.orchestration.tools import (
    fetch_products_by_category, inject_compliance,
    deterministic_audit, create_draft, record_run,
    record_review_attempt, get_published_count, get_published_titles
)

app = FastAPI(title="TestFlow Tool Server")

POST /tools/fetch_products        body: {category_id, limit?, explicit_products?}
                                  returns: {products: [...PRProduct...]}

POST /tools/inject_compliance     body: {html, affiliate_id, partner_id}
                                  returns: {html: "...", transforms_applied: int}

POST /tools/deterministic_audit   body: {html}
                                  returns: {passed: bool, errors: [...], warnings: [...]}

POST /tools/create_draft          body: {article: {...Article...}, site: "sites/site-one.yaml"}
                                  returns: {post_id: int, post_url: "https://..."}

POST /tools/record_run            body: {run_id, topic, keyword, category_id, article_type, status, stats}
                                  returns: {ok: true}

GET  /tools/published_titles      query: site_name, limit?
                                  returns: {titles: ["title 1", ...]}  # for internal linking context

GET  /health                      returns: {status: "ok"}
```

The skill document (`skills/affiliate-pipeline.md`) tells OpenClaw the base URL and each endpoint's parameters.

---

## 9b-plugin. `openclaw-plugin-testflow/` - Native OpenClaw tool plugin

This TypeScript package registers the Python tools as native OpenClaw tools. OpenClaw calls them by name (not by HTTP URL). The plugin also adds an approval gate via `before_tool_call`.

**Why a plugin instead of just calling the Python tool server via web_fetch?**
- Tools show up in `/tools` catalog - OpenClaw knows their names and parameter schemas at startup
- No `web_fetch` HTTP calls in the skill document - cleaner instructions
- `before_tool_call` hook enables a proper approval gate before WP publish
- `testflow_create_draft` can be `optional: true` - users must explicitly allowlist it for safety

### Folder structure
```
openclaw-plugin-testflow/
  src/
    index.ts          # defineToolPlugin entry
    client.ts         # thin HTTP client for Python tool server
  package.json
  openclaw.plugin.json  # generated by `openclaw plugins build`
  tsconfig.json
```

### `src/client.ts` - HTTP wrapper for Python tool server
```typescript
const BASE_URL = process.env.TESTFLOW_TOOL_SERVER ?? "http://localhost:8000";

async function callTool(path: string, body: unknown): Promise<unknown> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`TestFlow tool server error: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getTool(path: string): Promise<unknown> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`TestFlow tool server error: ${res.status}`);
  return res.json();
}

export { callTool, getTool };
```

### `src/index.ts` - defineToolPlugin
```typescript
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { callTool, getTool } from "./client.js";

export default defineToolPlugin({
  id: "testflow",
  name: "TestFlow Affiliate Pipeline",
  description: "Fetch products, run compliance checks, and publish WP drafts for the affiliate pipeline.",

  tools: (tool) => [

    // --- Fetch products from PriceRunner via Python tool server ---
    tool({
      name: "testflow_fetch_products",
      label: "Fetch PriceRunner Products",
      description: "Fetch product data for a PriceRunner category. Returns products with affiliate URLs.",
      parameters: Type.Object({
        category_id: Type.Number({ description: "Numeric PriceRunner category ID." }),
        limit: Type.Optional(Type.Number({ description: "Max products (default 10)." })),
        explicit_products: Type.Optional(Type.Array(Type.String(), {
          description: "Filter to these product names only (for versus/single-review)."
        })),
      }),
      execute: ({ category_id, limit, explicit_products }) =>
        callTool("/tools/fetch_products", { category_id, limit, explicit_products }),
    }),

    // --- Inject compliance params/disclosure into HTML ---
    tool({
      name: "testflow_inject_compliance",
      label: "Inject Compliance",
      description: "Add affiliate disclosure, ?ref-site= params, and widget to article HTML.",
      parameters: Type.Object({
        html: Type.String({ description: "Raw article body HTML." }),
        affiliate_id: Type.String({ description: "PriceRunner ref-site ID." }),
        partner_id: Type.String({ description: "PriceRunner partnerId for widget." }),
      }),
      execute: ({ html, affiliate_id, partner_id }) =>
        callTool("/tools/inject_compliance", { html, affiliate_id, partner_id }),
    }),

    // --- Deterministic safety audit ---
    tool({
      name: "testflow_deterministic_audit",
      label: "Deterministic Audit",
      description: "Run rule-based compliance checks on article HTML. Returns passed/errors/warnings.",
      parameters: Type.Object({
        html: Type.String({ description: "Article HTML to audit." }),
      }),
      execute: ({ html }) => callTool("/tools/deterministic_audit", { html }),
    }),

    // --- Create WordPress draft (requires approval) ---
    tool({
      name: "testflow_create_draft",
      label: "Create WP Draft",
      description: "Publish the article as a WordPress draft. REQUIRES HUMAN APPROVAL before executing.",
      optional: true,  // user must explicitly allowlist this tool
      parameters: Type.Object({
        article: Type.Object({
          title: Type.String(),
          slug: Type.String(),
          body_html: Type.String(),
          yoast_meta: Type.Object({
            focus_keyword: Type.String(),
            seo_title: Type.String(),
            meta_description: Type.String(),
          }),
          categories: Type.Array(Type.String()),
          tags: Type.Array(Type.String()),
          featured_image_url: Type.Optional(Type.String()),
        }),
        site: Type.String({ description: "Site config path, e.g. sites/site-one.yaml." }),
      }),
      execute: ({ article, site }) => callTool("/tools/create_draft", { article, site }),
    }),

    // --- Record pipeline run in SQLite ---
    tool({
      name: "testflow_record_run",
      label: "Record Run",
      description: "Save pipeline run metadata to the SQLite state database.",
      parameters: Type.Object({
        run_id: Type.String(),
        topic: Type.String(),
        keyword: Type.String(),
        category_id: Type.Number(),
        article_type: Type.String(),
        status: Type.String({ description: "success|aborted|failed" }),
        stats: Type.Optional(Type.Object({}, { additionalProperties: true })),
      }),
      execute: (params) => callTool("/tools/record_run", params),
    }),

    // --- Get published article titles for internal linking ---
    tool({
      name: "testflow_published_titles",
      label: "Published Titles",
      description: "Get titles of published articles on a site (for internal linking in SEO pass).",
      parameters: Type.Object({
        site_name: Type.String(),
        limit: Type.Optional(Type.Number()),
      }),
      execute: ({ site_name, limit }) =>
        getTool(`/tools/published_titles?site_name=${site_name}${limit ? `&limit=${limit}` : ""}`),
    }),

  ],
});
```

### Approval gate hook (`before_tool_call` on `testflow_create_draft`)

Add this to the plugin in a separate `definePluginEntry` wrapper, or alongside the tool plugin using a hybrid entry. This intercepts `testflow_create_draft` and pauses the pipeline to require human approval:

```typescript
// In src/index.ts - extend definePluginEntry instead of defineToolPlugin for the hook:
api.on("before_tool_call", async (event) => {
  if (event.toolName !== "testflow_create_draft") return;

  const article = event.params.article as { title: string };
  return {
    requireApproval: {
      title: "Create WordPress Draft",
      description: `About to create WP draft: "${article.title}"\n\nApprove to publish to WordPress. Deny to abort without publishing.`,
      severity: "info",
      timeoutMs: 300_000,       // 5 minutes to decide
      timeoutBehavior: "deny",  // auto-deny if nobody responds
    },
  };
});
```

> **Note:** `defineToolPlugin` does not support hooks. For the approval gate, the plugin should use `definePluginEntry` (from `openclaw/plugin-sdk/plugin-entry`) instead, which provides full `api` access. The tool definitions above port directly - replace `tools: (tool) => [...]` with individual `api.registerTool(...)` calls inside `register(api)`.

### Build and install
```bash
cd openclaw-plugin-testflow
npm install
npm run build                              # tsc → dist/
openclaw plugins build --entry ./dist/index.js  # generates openclaw.plugin.json
openclaw plugins validate --entry ./dist/index.js
openclaw plugins install ./openclaw-plugin-testflow
# restart OpenClaw
```

### Allow `testflow_create_draft`
In OpenClaw config (`config.json5`), allowlist the publish tool:
```json5
{
  tools: {
    allow: ["testflow_create_draft"],  // required: optional tool must be explicitly allowed
  },
}
```

Or use `/tools allow testflow_create_draft` from chat.

---

## 9c. `src/testflow/db.py` - SQLite state database

SQLite file at `testflow_state.db` in the project root (gitignored).

```sql
-- Three tables

CREATE TABLE pipeline_runs (
    run_id          TEXT PRIMARY KEY,  -- UUID
    site_name       TEXT NOT NULL,
    topic           TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    category_id     INTEGER NOT NULL,
    article_type    TEXT NOT NULL,     -- best-of-list|single-review|versus|comparison|buying-guide
    status          TEXT NOT NULL,     -- success|aborted|failed
    post_id         INTEGER,           -- WP post ID (null if aborted before publish)
    post_url        TEXT,              -- WP draft URL (null if aborted)
    duration_sec    REAL,
    total_phases    INTEGER,           -- total OpenClaw reasoning phases called
    estimated_cost  REAL,              -- rough estimate (Phase 2 - left as 0 for MVP)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE review_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    phase       TEXT NOT NULL,         -- brief|article|optimization
    attempt     INTEGER NOT NULL,      -- 1-based
    passed      INTEGER NOT NULL,      -- 0|1
    score       REAL,                  -- 0-10
    feedback    TEXT,                  -- OpenClaw's review feedback text
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE published_articles (
    post_id     INTEGER PRIMARY KEY,
    site_name   TEXT NOT NULL,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    title       TEXT NOT NULL,
    slug        TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    article_type TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Why SQLite?** Zero infrastructure. Works on any machine without a server. The DB is a run log, not a queue - reads are infrequent and writes are tiny. `get_published_titles()` does a simple `SELECT title FROM published_articles WHERE site_name = ?`.

---

## 9d. `src/testflow/compliance/rules.py` - COMPLIANCE_RULES

Single source of truth for all compliance rules. Imported by the audit function, the inject function, and injected into the Article context string so OpenClaw knows what it must produce.

```python
COMPLIANCE_RULES = {
    "disclosure": {
        "required": True,
        "position": "top",   # must be first element in body
        "html": '<div class="affiliate-disclosure"><p>Denne artikel indeholder affiliate-links. Vi kan modtage en kommission, hvis du køber via vores links - uden ekstra omkostninger for dig.</p></div>',
        "check": "div.affiliate-disclosure must exist as first child of body"
    },
    "affiliate_links": {
        "domain": "pricerunner.dk",
        "ref_param": "ref-site",        # ?ref-site={PRICERUNNER_AFFILIATE_ID}
        "widget_param": "partnerId",    # in JS widget embed
        "required_rel": ["sponsored", "nofollow"],
        "required_target": "_blank",
        "check": "every <a> pointing to pricerunner.dk must have ?ref-site=, rel=sponsored nofollow, target=_blank"
    },
    "prohibited_claims": [
        "billigste pris garanteret",
        "laveste pris",
        "garanti for",
        "vi garanterer",
    ],
    "widget": {
        "required": True,
        "check": "body must contain <div class='pr-widget'> or <script src='partner.pricerunner.dk'>"
    }
}
```

**Passed into OpenClaw's article context** as a JSON block so OpenClaw knows the rules during generation. **Also used deterministically** in `inject_compliance()` and `deterministic_audit()` - if OpenClaw misses something, these functions catch and fix it.

---

## 9e. `AGENTS.md` - OpenClaw project entry point

`AGENTS.md` sits in the project root. OpenClaw reads it on startup to understand the project. It answers: "What is this project? What can I do here? How do I start?"

> **Important:** OpenClaw automatically injects `AGENTS.md` into every sub-agent it spawns. This means any sub-agent used in Phase 2 will automatically know the tool server URL and key file paths - no extra configuration needed.

```markdown
# TestFlow - Affiliate Article Generator

## What this project does
Generates Danish affiliate marketing articles using PriceRunner product data,
publishes them as drafts to WordPress sites, and maintains content quality
through a structured review pipeline.

## How to use me (OpenClaw instructions)

### Before starting
1. Make sure `tool_server.py` is running: `./scripts/start.sh`
   If the server is unreachable, the `testflow_*` tools will fail immediately with a connection error. Tell the user to run `./scripts/start.sh` and stop.
2. Read `skills/affiliate-pipeline.md` - this is your complete instruction set
3. Read `sites/pricerunner-categories.yaml` - you need this to resolve category IDs

### Generating an article
Tell me what you want in natural language. Examples:
- "do a review of the Roomba j9+"
- "write a best-of article about robot vacuums"
- "compare Roomba j9+ vs Ecovacs Deebot X2"

I will read the skill document and call the tool server to run the pipeline.

### Tool server base URL
http://localhost:8000

### Key files
- `skills/affiliate-pipeline.md` - pipeline instructions and tool definitions
- `sites/pricerunner-categories.yaml` - category ID lookup table
- `sites/site-one.yaml` - primary test site config
- `affiliate/config.yaml` - affiliate rules (ref params, widget, disclosure)
- `templates/*.yaml` - article structure definitions (5 types)
```

---

## 9f. Support & Developer Files

These files make initial setup fast, daily development smooth, and the TypeScript plugin rebuildable after changes. They are all committed to the repo (except `.env` which is gitignored).

---

### `.env.example` - Full annotated template

Copy to `.env` and fill in real values. All keys must be present; the tool server and PriceRunner client will error on startup if any are missing.

```dotenv
# ─── PriceRunner ─────────────────────────────────────────────────────────────
# Appended as ?ref-site=XXX on every direct product link
PRICERUNNER_AFFILIATE_ID=your_ref_site_id

# Used as partnerId=XXX in the PriceRunner JS widget embed
# This is a DIFFERENT credential from AFFILIATE_ID - both are required
PRICERUNNER_PARTNER_ID=your_partner_id

# ─── WordPress (one App Password per site) ───────────────────────────────────
# WP Admin → Users → testflow-bot → Application Passwords → Generate
# Format: six groups of four characters, space-separated
WP_APP_PASSWORD_SITE_ONE=xxxx xxxx xxxx xxxx xxxx xxxx
WP_APP_PASSWORD_SITE_TWO=xxxx xxxx xxxx xxxx xxxx xxxx
# Add more sites here: WP_APP_PASSWORD_<NAME_UPPERCASE>

# ─── Tool server ─────────────────────────────────────────────────────────────
# The FastAPI server that the OpenClaw TS plugin calls
# Change only if port 8000 is in use
TOOL_SERVER_HOST=localhost
TOOL_SERVER_PORT=8000

# ─── OpenClaw plugin (optional override) ─────────────────────────────────────
# Overrides the tool server URL used by the TypeScript plugin
# Useful if you run the tool server on a different port or host
# Default: http://localhost:8000
# TESTFLOW_TOOL_SERVER=http://localhost:8000
```

---

### `pyproject.toml` - Full spec (deps + dev tooling + tasks)

```toml
[tool.poetry]
name = "testflow"
version = "0.1.0"
description = "Autonomous Danish affiliate marketing article generator"
authors = []
packages = [{ include = "testflow", from = "src" }]

[tool.poetry.dependencies]
python = "^3.11"
httpx = "^0.27"          # HTTP: PriceRunner API + WP REST
pydantic = "^2.7"        # Data models throughout
fastapi = "^0.111"       # tool_server.py
uvicorn = "^0.30"        # ASGI server for tool_server.py
beautifulsoup4 = "^4.12" # HTML parsing (compliance engine)
lxml = "^5.0"            # Faster BS4 parser
python-dotenv = "^1.0"   # .env loading
pyyaml = "^6.0"          # Site configs, templates, affiliate config
tenacity = "^8.3"        # Retry logic (PriceRunner + WP REST)

[tool.poetry.dev-dependencies]
pytest = "^8.0"
pytest-httpx = "^0.30"   # Mock httpx in tests
ruff = "^0.4"
mypy = "^1.10"
taskipy = "^1.12"        # `poetry run task <name>` shortcuts

# ─── Ruff (linter + formatter) ───────────────────────────────────────────────
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]  # pycodestyle, pyflakes, isort, naming, warnings, pyupgrade
ignore = []

# ─── Mypy ────────────────────────────────────────────────────────────────────
[tool.mypy]
python_version = "3.11"
strict = false                # enable gradually; start loose
ignore_missing_imports = true
check_untyped_defs = true

# ─── Pytest ──────────────────────────────────────────────────────────────────
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

# ─── Taskipy (dev task shortcuts) ────────────────────────────────────────────
# Usage: poetry run task <name>
[tool.taskipy.tasks]
start          = "uvicorn tool_server:app --host localhost --port 8000 --reload"
test           = "pytest"
lint           = "ruff check src/ tests/"
fmt            = "ruff format src/ tests/"
typecheck      = "mypy src/"
check          = "ruff check src/ tests/ && mypy src/"
build-plugin   = "bash scripts/build-plugin.sh"
install-plugin = "bash scripts/build-plugin.sh"   # build-plugin.sh installs by default
```

**Task cheat sheet:**
```
poetry run task start          # start tool server with hot reload
poetry run task test           # run all tests
poetry run task lint           # ruff lint check
poetry run task fmt            # auto-format with ruff
poetry run task check          # lint + typecheck together
poetry run task build-plugin   # rebuild TypeScript plugin after src/ changes
poetry run task install-plugin # reinstall the built plugin into OpenClaw
```

---

### `openclaw-plugin-testflow/package.json`

```json
{
  "name": "openclaw-plugin-testflow",
  "version": "1.0.0",
  "description": "OpenClaw tool plugin for the TestFlow affiliate pipeline",
  "type": "module",
  "main": "./dist/index.js",
  "scripts": {
    "build": "tsc",
    "plugin:build": "openclaw plugins build --entry ./dist/index.js",
    "plugin:validate": "openclaw plugins validate --entry ./dist/index.js",
    "plugin:install": "openclaw plugins install .",
    "dev": "tsc --watch"
  },
  "dependencies": {
    "@sinclair/typebox": "^0.32.0"
  },
  "peerDependencies": {
    "openclaw": "*"
  },
  "devDependencies": {
    "typescript": "^5.4.0"
  }
}
```

> **Install:** `cd openclaw-plugin-testflow && npm install` (one time). After editing `src/`, run `npm run build && npm run plugin:build && openclaw plugins install .` - or use `poetry run task build-plugin && poetry run task install-plugin` from the project root.

---

### `openclaw-plugin-testflow/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

---

### `config.json5` - OpenClaw project configuration

Place in the project root. OpenClaw reads this when launched from this directory.

```json5
{
  // Use the "coding" profile: enables exec, web_fetch, and file read/write tools.
  // Required for sessions_spawn (Phase 2 sub-agents) and HTTP tool calls.
  profile: "coding",

  // Skills to load at startup (skill docs injected into system prompt)
  skills: [
    "skills/affiliate-pipeline.md",
  ],

  // testflow_create_draft is marked optional: true in the plugin.
  // It must be explicitly listed here before OpenClaw will call it.
  tools: {
    allow: ["testflow_create_draft"],
  },

  // Plugin configuration
  plugins: {
    entries: {
      testflow: {
        hooks: {
          // Plugin only needs before_tool_call for the approval gate.
          // No need for conversation access (llm_input/llm_output).
          allowConversationAccess: false,
          timeoutMs: 30000,
          timeouts: {
            // Give the approval gate 10 minutes in case the user is away
            before_tool_call: 600000,
          },
        },
      },
    },
  },
}
```

---

### `scripts/start.sh` - Start tool server

```bash
#!/usr/bin/env bash
# scripts/start.sh
# Usage: ./scripts/start.sh [--reload]
set -euo pipefail

PORT=${TESTFLOW_PORT:-8000}
RELOAD_FLAG=""
[[ "${1:-}" == "--reload" ]] && RELOAD_FLAG="--reload"

echo "TestFlow - Starting tool server..."

# Check if already running
if curl -sf "http://localhost:$PORT/health" | grep -q '"ok"' 2>/dev/null; then
    echo "Tool server already running at http://localhost:$PORT"
    exit 0
fi

# Start in background
poetry run uvicorn tool_server:app --host localhost --port "$PORT" $RELOAD_FLAG &
TOOL_PID=$!
sleep 3

# Health check
if curl -sf "http://localhost:$PORT/health" | grep -q '"ok"'; then
    echo "Tool server healthy at http://localhost:$PORT (PID $TOOL_PID)"
else
    echo "ERROR: Tool server did not start. Check output above."
    exit 1
fi

echo ""
echo "Ready. Open OpenClaw in this directory and start writing articles."
echo "Tip: 'poetry run task test' to run tests, 'poetry run task lint' to lint."
```

---

### `scripts/build-plugin.sh` - Rebuild TypeScript plugin

Run after any changes to `openclaw-plugin-testflow/src/`. Also works after adding new tools.

```bash
#!/usr/bin/env bash
# scripts/build-plugin.sh
# Rebuilds and reinstalls the OpenClaw plugin after src/ changes.
# Usage: ./scripts/build-plugin.sh [--skip-install]
set -euo pipefail

SKIP_INSTALL=${1:-""}

echo "Building TypeScript plugin..."
cd openclaw-plugin-testflow

npm run build          || { echo "tsc build failed."; exit 1; }
npm run plugin:build   || { echo "openclaw plugin:build failed."; exit 1; }
npm run plugin:validate || { echo "plugin validation failed."; exit 1; }

if [[ "$SKIP_INSTALL" != "--skip-install" ]]; then
    npm run plugin:install
    echo "Plugin installed. Restart OpenClaw to load the updated version."
else
    echo "Plugin built (skipped install). Run 'openclaw plugins install .' manually."
fi

cd ..
```

---

## 9g. `runner.py` - CLI entry point

`runner.py` is the human-facing CLI for the TestFlow pipeline. It does **not** call any LLM - OpenClaw does all reasoning. `runner.py` handles:
1. Pre-flight checks (tool server health, env vars, site YAML validation)
2. Dry-run mode (fetches PriceRunner products + runs compliance pipeline without publishing)
3. Formatted prompt generation (prints the exact OpenClaw instruction to paste)

```python
#!/usr/bin/env python3
"""
runner.py - TestFlow CLI entry point.

Usage:
  # Pre-flight: verify setup is correct
  python runner.py --site sites/site-one.yaml --check

  # Dry run: fetch products + validate pipeline, no LLM, no publish
  python runner.py --site sites/site-one.yaml --products "Roomba j9+" --dry-run

  # Generate OpenClaw prompt (copy-paste into OpenClaw)
  python runner.py --site sites/site-one.yaml --products "Roomba j9+"
  python runner.py --site sites/site-one.yaml --topic "Bedste robotstøvsugere 2025" --template best-of-list

  # Category discovery helper
  python runner.py --discover "robotstøvsugere"
"""
import argparse
import sys
import httpx
from pathlib import Path
from testflow.models import SiteConfig
import yaml

TOOL_SERVER = "http://localhost:8000"

# ─── Argument parsing ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TestFlow pipeline CLI")
    p.add_argument("--site", help="Path to site YAML (e.g. sites/site-one.yaml)")
    p.add_argument("--products", nargs="+", help="Specific product name(s) for Mode A")
    p.add_argument("--topic",    help="Article topic (Mode B, free text)")
    p.add_argument("--keyword",  help="SEO keyword (optional override)")
    p.add_argument("--template", choices=["best-of-list","single-review","comparison","versus","buying-guide"])
    p.add_argument("--dry-run",  action="store_true", help="Fetch products + audit only; no LLM, no publish")
    p.add_argument("--check",    action="store_true", help="Pre-flight checks only")
    p.add_argument("--discover", metavar="QUERY",     help="Discover PriceRunner category IDs for a product type")
    return p

# ─── Pre-flight ───────────────────────────────────────────────────────────────

def check_tool_server() -> bool:
    """Returns True if tool server is healthy."""
    try:
        r = httpx.get(f"{TOOL_SERVER}/health", timeout=3)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False

def check_env() -> list[str]:
    """Returns list of missing required env vars."""
    import os
    required = ["PRICERUNNER_AFFILIATE_ID", "PRICERUNNER_PARTNER_ID"]
    return [k for k in required if not os.getenv(k)]

def load_site(path: str) -> SiteConfig:
    data = yaml.safe_load(Path(path).read_text())
    return SiteConfig(**data)

def preflight(site_path: str | None) -> bool:
    ok = True
    # Tool server
    if check_tool_server():
        print("✓ Tool server healthy")
    else:
        print("✗ Tool server not running. Start with: poetry run task start")
        ok = False
    # Env vars
    missing = check_env()
    if missing:
        print(f"✗ Missing env vars: {', '.join(missing)}")
        ok = False
    else:
        print("✓ Required env vars set")
    # Site YAML
    if site_path:
        try:
            site = load_site(site_path)
            print(f"✓ Site config loaded: {site.name} ({site.url})")
        except Exception as e:
            print(f"✗ Site config error: {e}")
            ok = False
    return ok

# ─── Dry run ─────────────────────────────────────────────────────────────────

def dry_run(site_path: str, products: list[str] | None, topic: str | None):
    """Fetch products from PriceRunner + run compliance pipeline. No LLM. No publish."""
    if not preflight(site_path):
        sys.exit(1)
    # Call tool server to fetch products
    payload = {"query": products[0] if products else topic, "limit": 5}
    r = httpx.post(f"{TOOL_SERVER}/tools/fetch_products_by_category", json=payload, timeout=20)
    r.raise_for_status()
    result = r.json()
    products_found = result.get("products", [])
    print(f"\n✓ Products fetched: {len(products_found)}")
    for p in products_found[:3]:
        print(f"  - {p['name']} | Fra {p['price_min']:.0f} kr | {p['url']}")
    print("\nDry run complete. No article generated, no draft created.")

# ─── Prompt generator ────────────────────────────────────────────────────────

def generate_prompt(products: list[str] | None, topic: str | None, template: str | None, site: str) -> str:
    """Print the OpenClaw instruction string to start the pipeline."""
    if products:
        instruction = f"Write an article about: {', '.join(products)}"
        if template:
            instruction += f" (use template: {template})"
    elif topic:
        instruction = f"Write an article: {topic}"
        if template:
            instruction += f" (use template: {template})"
    else:
        instruction = "Help me create a new affiliate article."
    instruction += f"\nSite: {site}"
    return instruction

# ─── Category discovery ───────────────────────────────────────────────────────

def discover_categories(query: str):
    r = httpx.post(f"{TOOL_SERVER}/tools/discover_categories", json={"query": query}, timeout=20)
    r.raise_for_status()
    cats = r.json().get("categories", [])
    if not cats:
        print(f"No categories found for '{query}'")
        return
    print(f"\nPriceRunner categories matching '{query}':")
    for c in cats[:10]:
        print(f"  {c['id']:>6}  {c['name']}  (parent: {c['parent']})")
    print("\nAdd the best match to sites/pricerunner-categories.yaml")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = build_parser().parse_args()

    if args.discover:
        discover_categories(args.discover)
        return

    if args.check:
        ok = preflight(args.site)
        sys.exit(0 if ok else 1)

    if args.dry_run:
        if not args.site:
            print("--site is required for --dry-run")
            sys.exit(1)
        dry_run(args.site, args.products, args.topic)
        return

    # Default: generate OpenClaw prompt
    if not args.site:
        print("--site is required")
        sys.exit(1)
    if not preflight(args.site):
        sys.exit(1)
    prompt = generate_prompt(args.products, args.topic, args.template, args.site)
    print("\n" + "─" * 60)
    print("Paste this into OpenClaw:")
    print("─" * 60)
    print(prompt)
    print("─" * 60)

if __name__ == "__main__":
    main()
```

**CLI reference:**

| Command | What it does |
|---------|-------------|
| `python runner.py --site ... --check` | Pre-flight only. Exits 0 if all checks pass. |
| `python runner.py --site ... --products "X" --dry-run` | Fetches products + validates compliance pipeline. No LLM. |
| `python runner.py --site ... --products "X"` | Runs preflight, prints formatted OpenClaw prompt. |
| `python runner.py --discover "robotstøvsugere"` | Shows PriceRunner category IDs for a search term. |

---

## 10. MVP 1 Delivery Checklist

### Developer support files
- [ ] `.env.example` exists with all required keys and comments - copy it to `.env` and fill in
- [ ] `pyproject.toml` includes `[tool.taskipy.tasks]` - `poetry run task start` launches the tool server
- [ ] `poetry run task test` runs pytest without errors (with mocked HTTP)
- [ ] `poetry run task lint` runs ruff with zero errors on `src/` and `tests/`
- [ ] `openclaw-plugin-testflow/package.json` exists - `npm install` inside that folder succeeds
- [ ] `openclaw-plugin-testflow/tsconfig.json` exists - `npm run build` compiles without errors
- [ ] `scripts/start.sh` launches the tool server and reports healthy
- [ ] `scripts/build-plugin.sh` builds, validates, and installs the TS plugin in one step
- [ ] `config.json5` exists in project root with `profile: "coding"` and the testflow plugin entry

### Infrastructure
- [ ] WordPress site live, REST API enabled (`/wp-json/wp/v2/` returns 200)
- [ ] Yoast SEO plugin installed and active
- [ ] `yoast-rest-bridge` plugin uploaded and activated (manual install via WP Admin)
- [ ] Plugin endpoint test: `GET /wp-json/yoast-bridge/v1/post/1/meta` returns 200
- [ ] `testflow-bot` WP user created with Editor role + Application Password in `.env`
- [ ] Both PriceRunner credentials in `.env`: `PRICERUNNER_AFFILIATE_ID` + `PRICERUNNER_PARTNER_ID`
- [ ] `poetry install` succeeds
- [ ] `sites/pricerunner-categories.yaml` populated with at least the test category IDs
- [ ] `scripts/start.sh` starts the tool server and reports healthy
- [ ] `GET http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] `AGENTS.md` exists in project root with correct tool server URL and key file paths
- [ ] `config.json5` in project root with `profile: "coding"` and `testflow_create_draft` in allow list
- [ ] OpenClaw plugin installed: `poetry run task install-plugin` completes without error
- [ ] OpenClaw can read `AGENTS.md` and `skills/affiliate-pipeline.md` on startup
- [ ] OpenClaw skill doc contains the full pipeline execution steps (Step 0 through Step 5)

### PriceRunner integration
- [ ] `PriceRunnerClient.fetch_products_by_category(category_id=1613, limit=5)` returns >= 1 `PRProduct`
- [ ] Returned products have `name`, `price_min`, `url`, `image_url`, `rating` fields populated
- [ ] `affiliate_url` property appends `?ref-site={PRICERUNNER_AFFILIATE_ID}` correctly
- [ ] API cache writes to `cache/pricerunner/` and is reused on second call
- [ ] Rate limiting: two rapid calls are spaced >= 1 second apart

### WordPress publisher
- [ ] `WordPressClient.get_or_create_category("Robotstøvsugere")` returns a WP category ID
- [ ] Second call returns same ID (idempotent - no duplicate categories created)
- [ ] `sideload_image(image_url)` creates a media attachment in WP and returns its ID
- [ ] `create_post(article)` creates a draft with correct title, body, categories, tags, featured image
- [ ] Draft status confirmed in WP Admin (not published)
- [ ] `set_yoast_meta()` - all 6 Yoast fields visible in WP Admin on the draft

### Templates
- [ ] All 5 template YAML files exist and parse without error
- [ ] `load_template("best-of-list")` returns a valid `ArticleTemplate` with all sections
- [ ] `load_template("single-review")` returns schema_type `Review`
- [ ] `list_templates()` returns all 5 types

### OpenClaw integration
- [ ] OpenClaw reads `AGENTS.md` and `skills/affiliate-pipeline.md` on startup without errors
- [ ] OpenClaw calls `POST /tools/fetch_products` and gets a valid product list back
- [ ] OpenClaw calls `POST /tools/inject_compliance` and gets modified HTML back
- [ ] OpenClaw calls `POST /tools/deterministic_audit` and gets pass/fail result back
- [ ] OpenClaw calls `POST /tools/create_draft` and the draft appears in WP Admin
- [ ] Mode A: telling OpenClaw "do a review of Roomba j9+" resolves to `single-review`, category_id=1613, Danish topic
- [ ] Mode A: "compare Roomba j9+ vs Ecovacs Deebot X2" resolves to `versus`
- [ ] Mode A: "de bedste robotstøvsugere" resolves to `best-of-list`, category_id=1613
- [ ] Mode B: OpenClaw calls tool server with explicit params straight through
- [ ] OpenClaw Brief phase produces valid `ContentBrief` JSON with all required fields
- [ ] OpenClaw Brief Review phase correctly rejects a vague or generic brief
- [ ] OpenClaw retries Brief phase with feedback on rejection (max 2 attempts)
- [ ] OpenClaw Article phase produces valid `ArticleDraft` JSON following template structure
- [ ] OpenClaw Article Review phase correctly fails a draft with missing disclosure or `ref-site`
- [ ] OpenClaw Article Review phase correctly passes a clean, compliant draft
- [ ] OpenClaw retries Article phase with structured issue feedback (max 3 attempts)
- [ ] OpenClaw SEO phase returns draft with improved heading structure and `yoast_meta`
- [ ] OpenClaw CRO phase returns draft with adjusted CTA placement and product ordering
- [ ] OpenClaw Optimization Review catches keyword stuffing from SEO phase
- [ ] OpenClaw Optimization Review passes a clean SEO+CRO draft
- [ ] OpenClaw retries SEO+CRO once with structured issues; aborts on second failure
- [ ] `inject_compliance()` tool adds disclosure, `?ref-site=` on all PriceRunner links, widget
- [ ] `deterministic_audit()` tool catches a draft missing the disclosure and returns `passed: false`
- [ ] Second site (`site-two.yaml`) can be targeted with no code changes

### runner.py
- [ ] `python runner.py --site sites/site-one.yaml --check` exits 0 with all checks green
- [ ] `python runner.py --discover "robotstøvsugere"` returns category IDs from PriceRunner
- [ ] `python runner.py --site sites/site-one.yaml --products "Roomba j9+" --dry-run` fetches products and exits 0

### End-to-end
- [ ] `python runner.py --site sites/site-one.yaml --products "Roomba j9+"` prints formatted OpenClaw prompt
- [ ] Pasting the prompt into OpenClaw triggers the pipeline and creates a WP draft
- [ ] WP draft body contains `?ref-site={PRICERUNNER_AFFILIATE_ID}` on all PriceRunner links
- [ ] WP draft has affiliate disclosure `<div class="affiliate-disclosure">` at top of body
- [ ] WP draft has Yoast focus keyword, meta description, and SEO title populated
- [ ] WP draft has featured image (sideloaded from PriceRunner CDN)
- [ ] WP draft has correct category and tag assigned
- [ ] `testflow_state.db` contains a `pipeline_runs` record for the run with status and stats

### Tests
- [ ] `pytest tests/test_compliance.py` - all pass (inject_compliance + deterministic_audit)
- [ ] `pytest tests/test_publisher.py` - all pass (mocked with pytest-httpx)
- [ ] `pytest tests/test_pricerunner.py` - all pass (mocked responses, no real HTTP)
- [ ] `pytest tests/test_tool_server.py` - all pass (FastAPI TestClient, no real tool server needed)

---

## 10b. Test File Specs

Three test files cover the deterministic Python layer. No LLM calls, no live HTTP. All external calls are mocked.

---

### `tests/test_compliance.py`

Tests the compliance engine in isolation. Input: raw HTML. Output: transformed HTML + audit result.

```python
import pytest
from testflow.compliance.inject_compliance import inject_compliance
from testflow.compliance.rules import COMPLIANCE_RULES
from testflow.orchestration.tools import deterministic_audit

# ─── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_ARTICLE = """
<article>
  <h1>Bedste Robotstøvsugere</h1>
  <p>Se de bedste modeller på <a href="https://www.pricerunner.dk/cl/1613/Robotstøvsugere">PriceRunner</a>.</p>
  <p>Køb Roomba j9+ hos <a href="https://www.pricerunner.dk/pl/1234/Roomba">PriceRunner</a>.</p>
</article>
"""

# ─── inject_compliance ────────────────────────────────────────────────────────

def test_disclosure_injected_at_top():
    result = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    assert 'class="affiliate-disclosure"' in result
    # Must appear before the first <h1>
    assert result.index("affiliate-disclosure") < result.index("<h1>")

def test_ref_param_added_to_pricerunner_links():
    result = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    assert "ref-site=TEST123" in result
    # Every pricerunner.dk link must have the ref param
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "lxml")
    pr_links = [a for a in soup.find_all("a") if "pricerunner.dk" in a.get("href", "")]
    assert all("ref-site=TEST123" in a["href"] for a in pr_links)

def test_links_get_sponsored_nofollow():
    result = inject_compliance(MINIMAL_ARTICLE, affiliate_id="TEST123", partner_id="PART456")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "lxml")
    pr_links = [a for a in soup.find_all("a") if "pricerunner.dk" in a.get("href", "")]
    for link in pr_links:
        assert "sponsored" in link.get("rel", [])
        assert "nofollow" in link.get("rel", [])

def test_idempotent_double_inject():
    """Running inject_compliance twice must not double-inject disclosure or ref params."""
    once  = inject_compliance(MINIMAL_ARTICLE, "TEST123", "PART456")
    twice = inject_compliance(once, "TEST123", "PART456")
    assert twice.count("affiliate-disclosure") == 1
    assert twice.count("ref-site=TEST123") == once.count("ref-site=TEST123")

# ─── deterministic_audit ─────────────────────────────────────────────────────

def test_audit_passes_after_inject():
    injected = inject_compliance(MINIMAL_ARTICLE, "TEST123", "PART456")
    report = deterministic_audit(injected)
    assert report.passed, f"Audit failed: {report.errors}"

def test_audit_fails_without_disclosure():
    # Article without disclosure
    html = "<article><p>Se <a href='https://www.pricerunner.dk/pl/1?ref-site=X'>produkt</a>.</p></article>"
    report = deterministic_audit(html)
    assert not report.passed
    assert any("disclosure" in e.lower() for e in report.errors)

def test_audit_fails_without_ref_param():
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <a href="https://www.pricerunner.dk/pl/1234">link without ref</a>
    </article>"""
    report = deterministic_audit(html)
    assert not report.passed
    assert any("ref-site" in e for e in report.errors)

def test_audit_flags_prohibited_claim():
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <p>Dette er billigst i Danmark <a href="https://www.pricerunner.dk/pl/1?ref-site=X">link</a>.</p>
    </article>"""
    report = deterministic_audit(html)
    assert not report.passed
    assert any("billigst i Danmark" in e for e in report.errors)
```

---

### `tests/test_publisher.py`

Tests the WordPress client in isolation. All HTTP calls mocked with `pytest-httpx`.

```python
import pytest
from pytest_httpx import HTTPXMock
from testflow.publisher.client import WordPressClient
from testflow.models import Article, YoastMeta

SITE_URL = "https://www.site-one.dk"

@pytest.fixture
def client():
    return WordPressClient(SITE_URL, "testflow-bot", "fake-app-password")

@pytest.fixture
def minimal_article():
    return Article(
        title="Test artikel",
        slug="test-artikel",
        excerpt="En test",
        body_html="<p>Indhold</p>",
        yoast_meta=YoastMeta(
            focus_keyword="test",
            meta_description="Test meta",
            seo_title="Test | Site One",
        ),
        categories=["Robotstøvsugere"],
        tags=["test"],
    )

def test_create_post_sends_draft_status(httpx_mock: HTTPXMock, client, minimal_article):
    # Mock: category lookup (not found), category create, post create, yoast
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/categories?search=Robotstøvsugere", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/categories", json={"id": 5})
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/tags?search=test", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/tags", json={"id": 10})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/posts",
                            json={"id": 42, "link": f"{SITE_URL}/?p=42"})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/yoast-bridge/v1/post/42/meta",
                            json={"updated": {"focus_keyword": "test"}})

    result = client.create_post(minimal_article)
    assert result.post_id == 42

def test_create_post_uses_existing_category(httpx_mock: HTTPXMock, client, minimal_article):
    """Should not create a new category if one already exists."""
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/categories?search=Robotstøvsugere",
                            json=[{"id": 5, "name": "Robotstøvsugere"}])
    # No POST to /categories expected
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/tags?search=test", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/tags", json={"id": 10})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/posts",
                            json={"id": 43, "link": f"{SITE_URL}/?p=43"})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/yoast-bridge/v1/post/43/meta",
                            json={"updated": {}})
    result = client.create_post(minimal_article)
    assert result.post_id == 43
    # Only one categories request (the GET), no POST to categories
    cat_requests = [r for r in httpx_mock.get_requests() if "/categories" in str(r.url) and r.method == "POST"]
    assert len(cat_requests) == 0
```

---

### `tests/test_pricerunner.py`

Tests `PriceRunnerClient` with mocked HTTP. No real PriceRunner calls.

```python
import pytest
import json
from unittest.mock import patch, MagicMock
from testflow.content.pricerunner import PriceRunnerClient
from testflow.models import PRProduct

MOCK_PRODUCT_RESPONSE = {
    "products": [
        {
            "id": "1234567",
            "name": "iRobot Roomba j9+",
            "price": {"min": 4199, "max": 5499},
            "url": "/pl/1234567/iRobot-Roomba-j9-plus",
            "image": {"url": "https://cdn.pricerunner.com/images/roomba.jpg"},
            "rating": {"score": 4.7, "count": 312},
            "merchantCount": 8,
            "category": {"id": 1613, "name": "Robotstøvsugere"},
        }
    ]
}

@pytest.fixture
def client():
    return PriceRunnerClient()

def test_fetch_products_returns_prproduct_list(client):
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE):
        products = client.fetch_products_by_category(1613, limit=5)
    assert len(products) == 1
    assert isinstance(products[0], PRProduct)
    assert products[0].name == "iRobot Roomba j9+"

def test_affiliate_url_appends_ref_param(client):
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE):
        products = client.fetch_products_by_category(1613)
    with patch.dict("os.environ", {"PRICERUNNER_AFFILIATE_ID": "my-ref-id"}):
        assert "ref-site=my-ref-id" in products[0].affiliate_url

def test_cache_is_used_on_second_call(client, tmp_path):
    """Second call for same category should read from cache, not make HTTP request."""
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE) as mock_get:
        client.fetch_products_by_category(1613)
        client.fetch_products_by_category(1613)
    # _get should only be called once (second is cache hit)
    assert mock_get.call_count == 1

def test_discover_categories_returns_matches(client):
    mock_tree = {
        "children": [
            {"id": "cl1613", "name": "Robotstøvsugere", "children": []},
            {"id": "cl67",   "name": "Støvsugere",      "children": []},
        ]
    }
    with patch.object(client, "_get", return_value=mock_tree):
        results = client.discover_categories("støvsugere")
    assert len(results) >= 1
    assert any(r["id"] == 1613 for r in results)
```

---

### `tests/test_tool_server.py`

Tests the FastAPI tool server using `TestClient` (no running server needed).

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from tool_server import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_fetch_products_endpoint():
    mock_products = [MagicMock(model_dump=lambda: {"name": "Roomba", "price_min": 3999})]
    with patch("tool_server.PriceRunnerClient") as MockClient:
        MockClient.return_value.fetch_products_by_category.return_value = mock_products
        r = client.post("/tools/fetch_products_by_category",
                        json={"category_id": 1613, "limit": 5})
    assert r.status_code == 200
    assert "products" in r.json()

def test_inject_compliance_endpoint():
    html = "<article><p>Test <a href='https://www.pricerunner.dk/pl/1'>link</a></p></article>"
    r = client.post("/tools/inject_compliance",
                    json={"html": html, "affiliate_id": "TEST", "partner_id": "PART"})
    assert r.status_code == 200
    body = r.json()
    assert "html" in body
    assert "transforms_applied" in body

def test_deterministic_audit_endpoint_passes():
    # Fully compliant HTML
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <a href="https://www.pricerunner.dk/pl/1?ref-site=X" rel="sponsored nofollow">link</a>
    </article>"""
    r = client.post("/tools/deterministic_audit", json={"html": html})
    assert r.status_code == 200
    assert r.json()["passed"] is True

def test_discover_categories_endpoint():
    mock_cats = [{"name": "Robotstøvsugere", "id": 1613, "parent": "Rengøring"}]
    with patch("tool_server.PriceRunnerClient") as MockClient:
        MockClient.return_value.discover_categories.return_value = mock_cats
        r = client.post("/tools/discover_categories", json={"query": "robotstøvsugere"})
    assert r.status_code == 200
    assert len(r.json()["categories"]) >= 1
```

---

## 11. Site Optimization Pipeline (separate, scheduled)

The generation pipeline handles *new* content. The optimization pipeline handles *existing* content. They run independently on different schedules.

### Why it's separate

The generation pipeline cannot retroactively update already-published posts. When Article B is published, it can link forward to existing articles - but existing articles cannot link back to B unless we go back and edit them. That retroactive operation, plus all the health checks below, belongs in a dedicated scheduled pipeline.

### Pipeline flow

```
optimizer.py --site sites/example-site.yaml  (runs weekly, or after every N new articles)
  |
  +-- [tool] fetch_all_published(site_config)
  |       -> list[PublishedArticle { post_id, url, title, keyword, html, published_at }]
  |
  +-- [tool] broken_link_checker()          # deterministic HTTP checks, no LLM
  |       -> list[BrokenLink { post_id, url, status_code }]
  |       auto-fix: redirects (update href)
  |       flag:     404 / dead links
  |
  +-- [tool] orphan_page_detector()         # deterministic, reads WP link graph
  |       -> list[OrphanPage { post_id, title, inbound_link_count }]
  |       flag: any page with 0 inbound internal links
  |
  +-- [tool] pricerunner_staleness_checker()  # HTTP + price comparison
  |       -> list[StaleProduct { post_id, product_url, reason }]
  |       reasons: url_dead | price_shift_gt_30pct | product_discontinued
  |       flag all: human or refresh agent decides action
  |
  +-- [tool] thin_content_detector()        # word count from WP REST API
  |       -> list[ThinArticle { post_id, word_count, threshold }]
  |       flag: articles below configured word count minimum
  |
  +-- [spawn] Link Opportunity Agent        # intelligent, uses LLM
  |       context: all article titles, slugs, keywords, existing internal links
  |       task:    identify missing reciprocal link opportunities
  |       returns: list[LinkOpportunity { from_post_id, to_post_id, anchor_text, context_hint }]
  |
  +-- FOR EACH LinkOpportunity:
  |     [spawn] Link Injector Agent
  |         context: from_article HTML, link opportunity details
  |         task:    find the best sentence to add the internal link naturally
  |         returns: updated HTML with link inserted
  |     [tool] update_post(post_id, updated_html)
  |     [tool] record_optimization(post_id, type="internal_link", details)
  |
  +-- [tool] write_optimization_report(site, findings, fixes_applied, flags_raised)
```

### Sub-agent contracts

**Link Opportunity Agent**
```
TASK: Identify internal linking opportunities across these articles
ARTICLES: {list of { post_id, title, slug, keyword, excerpt }}
EXISTING LINKS: {current internal link map from state DB}

Find pairs where Article A should link to Article B but currently does not.
Prioritise: new articles with no inbound links, topically related articles,
articles sharing product categories.

Return JSON array:
[{ "from_post_id": int, "to_post_id": int,
   "anchor_text": "natural anchor text",
   "context_hint": "which section or topic in the source article" }]
```

**Link Injector Agent**
```
TASK: Insert one internal link into this article
ARTICLE HTML: {html}
LINK TO INSERT: { "href": "{slug}", "anchor_text": "{anchor}", "context_hint": "{hint}" }

Find the most natural sentence to add this link. Do not force it.
If no good location exists, return { "inserted": false, "reason": "..." }.
Otherwise return { "inserted": true, "updated_html": "..." }.
```

### What gets auto-fixed vs. flagged

| Finding | Action | Notes |
|---------|--------|-------|
| Missing internal links | Auto-fix via Link Injector Agent | Logged in DB |
| Redirect (3xx) on outbound link | Auto-fix (update href to final URL) | Logged |
| Dead link (404) on outbound link | Flag only | Human decides replacement |
| Pricerunner product URL dead | Flag + pause article (set to draft) | Avoids broken affiliate links live |
| Orphan page | Queued for next Link Opportunity run | Not immediately fixed |
| Thin content | Flag only | Queued for content refresh (Phase 4) |

### Folder additions

```
src/testflow/
└── optimization/
    ├── __init__.py
    ├── pipeline.py           # run_optimization_pipeline(site_config)
    ├── broken_links.py       # broken_link_checker(), auto_fix_redirect()
    ├── orphan_detector.py    # orphan_page_detector()
    ├── staleness.py          # pricerunner_staleness_checker()
    ├── thin_content.py       # thin_content_detector()
    └── internal_links.py     # Link Opportunity Agent + Link Injector Agent prompts
```

```
optimizer.py                  # CLI entry point (mirrors runner.py for generation)
```

### CLI usage

```
python optimizer.py --site sites/example-site.yaml            # full optimization run
python optimizer.py --site sites/example-site.yaml --check broken-links   # single check
python optimizer.py --site sites/example-site.yaml --check internal-links
python optimizer.py --site sites/example-site.yaml --dry-run  # report only, no writes
```

### Scheduling

- **After every new article:** `run_optimization_pipeline(site, checks=["internal-links"])` - just the link pass, triggered by `runner.py` at the end of a successful publish
- **Weekly:** full run (all checks) via cron or GitHub Actions `schedule:`
- **State DB table:** `optimization_log { id, site, post_id, check_type, action, details, created_at }`

---

## 12. Logging & Observability

Every pipeline run gets a `run_id` (UUID). All log entries, DB records, and sub-agent calls are tagged with it so a full run can be traced end to end.

### Structured logging

```python
# src/testflow/orchestration/logging.py
import logging, json, uuid
from datetime import datetime

def generate_run_id() -> str:
    return str(uuid.uuid4())

def log_pipeline_event(run_id: str, stage: str, event: str, details: dict = None):
    """Structured JSON log entry for every pipeline event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "run_id": run_id,
        "stage": stage,
        "event": event,
        "details": details or {}
    }
    logging.info(json.dumps(entry))
```

### What gets logged

| Event | Stage | Details |
|-------|-------|---------|
| `pipeline_start` | init | topic, keyword, category_id, article_type, runtime, explicit_products |
| `products_fetched` | fetch | count, category_id |
| `products_filtered` | fetch | count_after_filter, explicit_products (for versus/single-review) |
| `products_empty` | fetch | category_id - pipeline aborts |
| `sub_agent_call` | brief/article/seo/cro/opt_review | model_tier, prompt_length, response_length, tokens_used |
| `review_result` | brief/article/optimization | passed, score, attempt, issues_count |
| `compliance_injected` | compliance | transforms_applied (disclosure, ref_params, widget) |
| `audit_result` | audit | passed, errors - from deterministic_audit() post-inject |
| `draft_created` | publish | post_id, post_url, wp_status=draft |
| `pipeline_abort` | any | reason, stage |
| `pipeline_complete` | done | total_duration_seconds, total_sub_agent_calls, total_tokens, estimated_cost_usd |

### Cost tracking

Each `spawn_sub_agent()` call returns token usage alongside the JSON response. The pipeline accumulates these into a `PipelineRunStats` object stored in the state DB.

```python
class PipelineRunStats(BaseModel):
    run_id: str
    topic: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_sub_agent_calls: int = 0
    duration_seconds: float = 0
    estimated_cost_usd: float = 0  # calculated from token counts + model pricing
```

State DB table: `pipeline_runs { run_id, site, topic, keyword, article_type, status, stats_json, created_at, completed_at }`

---

## 13. `.gitignore`

```gitignore
# Secrets
.env

# State
testflow_state.db

# PriceRunner API cache
cache/

# Python
__pycache__/
*.pyc
*.pyo
.venv/
dist/
*.egg-info/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
```

---

## 14. README.md

The project ships with a `README.md` covering:

```markdown
# TestFlow - Affiliate Article Generator

Autonomous pipeline for generating SEO-optimised Danish affiliate articles
and publishing them to WordPress with Yoast SEO metadata.

## Prerequisites
- Python 3.11+
- Poetry 1.8+
- WordPress site with REST API enabled
- Yoast SEO plugin installed
- Yoast REST Bridge plugin installed (see wp-plugin/)

## Quick Start
1. Clone the repo
2. `poetry install`
3. Copy `.env.example` to `.env` and fill in credentials
4. Configure your site in `sites/site-one.yaml`
5. Install the Yoast REST Bridge plugin on your WordPress site
6. Run: `python runner.py --site sites/site-one.yaml --topic "..." --keyword "..." --template best-of-list`

## Runtime Configuration
Set `TESTFLOW_RUNTIME` in `.env` to choose the orchestrator backend:
- `claude-api` (default) - direct Anthropic API calls
- `claude-code` - Claude Code CLI subprocess
- `openclaw` - OpenClaw sub-agent spawning
- `augment` - Augment Agent sub-agents

## Project Structure
(folder tree summary)

## Article Types
(table of available templates)

## Adding a New Site
1. Create `sites/my-new-site.yaml` with name, url, username
2. Add `WP_APP_PASSWORD_MY_NEW_SITE` to `.env`
3. Install the Yoast REST Bridge plugin on the new site
4. Run with `--site sites/my-new-site.yaml`

## Optimization Pipeline
`python optimizer.py --site sites/site-one.yaml` for full health checks.

## Development
- `pytest` to run tests
- `ruff check .` for linting
- `mypy src/` for type checking
```

---

## 15. Security & Operational Notes

- **Never commit `.env`** - covered by `.gitignore`
- **`testflow-bot`** with `Editor` role only - not admin
- **PriceRunner API:** Uses the unofficial internal API (no auth required). `PriceRunnerClient._get()` enforces: (1) min 1.5s base delay + 0-0.8s random jitter between every request to avoid predictable patterns, (2) UA rotation through a pool of 6 realistic browser strings on every call, (3) full browser-like headers (`Referer`, `Origin`, `sec-fetch-*`, `sec-ch-ua`) to pass basic bot detection, (4) automatic exponential backoff on 429/503/timeout via `tenacity` (up to 4 attempts, 3s→6s→12s→24s). Results cached to `cache/pricerunner/` (24h for products, 30 days for category trees) to minimize total API calls. If PriceRunner grants official affiliate API access, swap to that endpoint - same data, stable contract, no scraping concerns.
- **Two PriceRunner credentials:** `PRICERUNNER_AFFILIATE_ID` is for `?ref-site=` on direct links. `PRICERUNNER_PARTNER_ID` is for widget embeds. Keep both in `.env`, never hardcoded.
- **Deterministic audit is mandatory:** `deterministic_audit()` runs after `inject_compliance()` and before `create_post()`. If it fails, the pipeline aborts - no draft is created. No bypass path in `runner.py`.
- **Draft-only publishing:** The pipeline never publishes live. It always creates a WP draft. Human reviews and clicks Publish in WP Admin. This is the only safeguard needed at MVP scale.
- **SQLite:** `testflow_state.db` in project root, covered by `.gitignore`
- **API keys:** `ANTHROPIC_API_KEY` is only used by `ClaudeAPIRuntime`. Other runtimes may use their own auth mechanisms.

---

## 16. Phase 2+ Roadmap

| Phase | Feature | Notes |
|-------|---------|-------|
| 2 | Automatic publishing | Add `--publish` flag to flip draft to live after human review period; or a review-and-publish CLI command |
| 2 | Multi-site orchestration | Loop `sites/*.yaml`; per-site article quotas tracked in state DB |
| 2 | Cron scheduling | GitHub Actions `schedule:` or system cron - run `runner.py` on a topic queue automatically. Design TBD after MVP is validated. |
| 2 | Optimization pipeline - full run | `optimizer.py`: broken links, orphan pages, PriceRunner staleness, thin content detection |
| 2 | Backward internal linking | `optimizer.py --check internal-links`: have old articles link back to new ones via Link Opportunity + Injector agents |
| 3 | Automated keyword research | Ahrefs/SEMrush API replacing LLM keyword ideation stub |
| 3 | AI image generation | DALL-E/Flux generated hero images, uploaded to WP Media Library via REST |
| 3 | Analytics + Search Console | GA4/GSC API - feed performance data back to keyword selection; surface low-CTR articles for title/meta refresh |
| 3 | Custom PriceRunner widget | Build own comparison widget from API data instead of using PriceRunner's JS embed - full control over design and tracking |
| 4 | Content refresh | Re-run article pipeline on underperforming articles on schedule |
| 4 | A/B title testing | Two title variants, pick winner after 2-week CTR data window |
| 4 | Alerting | Slack/email on draft created, pipeline failure, compliance block |

---

*Plan generated 2026-05-27 for TestFlow project.*
