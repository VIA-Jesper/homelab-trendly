# Trendly v2

Agentic affiliate article pipeline for Danish WordPress sites. Finds content gaps via PriceRunner, generates briefs, writes articles through an AI agent, validates compliance, and publishes to WordPress.

The agent (Augment/Claude) drives everything via CLI commands. Hard compliance gates run server-side on every `validate` and `publish` call and cannot be bypassed.

## Supported sites

| Key | Description |
|-----|-------------|
| `techblog` | Danish tech reviews (laptops, phones, headphones, TVs) |
| `husforbegyndere` | Danish home/garden (coffee machines, robot vacuums, grills) |

---

## Setup

### Prerequisites

- Node.js 20+
- A WordPress site with REST API enabled (one per site)
- PriceRunner affiliate partner ID (one per site)

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# techblog
WP_TECHBLOG_USER=your-wp-username
WP_TECHBLOG_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_TECHBLOG_BASE_URL=https://your-techblog.dk
PR_TECHBLOG_PARTNER_ID=your-pricerunner-partner-id

# husforbegyndere
WP_HUS_USER=your-wp-username
WP_HUS_PASS=xxxx xxxx xxxx xxxx xxxx xxxx
WP_HUS_URL=https://husforbegyndere.dk
PR_HUS_PARTNER_ID=your-pricerunner-partner-id
```

**WordPress Application Password:** WP Admin - Users - Your Profile - Application Passwords. Create one named "Trendly". Copy the value (spaces and all).

### 3. Run setup check

```bash
npm run cli -- setup
```

Validates env vars, creates `data/trendly.db` (SQLite), and tests WP connectivity for each site.

### 4. Optional: install CLI globally

```bash
npm link
trendly setup   # now works without npm run cli --
```

Without `npm link`, prefix all commands with `npm run cli --`:

```bash
npm run cli -- generate --site techblog
```

### Upgrading from v1

If you have `data/content-registry.json` or `data/published-log.json` from v1:

```bash
npm run migrate
```

Imports the data into SQLite and renames the old files to `.legacy`.

---

## Usage

### CLI quick reference

```
trendly setup                                        check env + DB + WP connectivity
trendly generate --site <site>                       find content gap, create brief + run_id
trendly generate --site <site> --category <slug>     force a specific category
trendly validate --run <id> --article <file>         run compliance check against brief
trendly publish  --run <id> --article <file>         save as WordPress draft
trendly publish  --run <id> --article <file> --live  publish live immediately
trendly runs                                         list recent runs
trendly runs --site techblog --status published      filter by site or status
trendly runs show <id>                               full run details + validation result
```

Add `--json` to any command for machine-readable output.

### Manual workflow (step by step)

**Step 1 - Find a content gap and get a brief**

```bash
trendly generate --site techblog
```

The CLI picks the category with the most fresh (unpublished) products that is not in cooldown. It prints a brief and a **Run ID** - save the Run ID, you need it for every subsequent step.

To force a specific category:

```bash
trendly generate --site techblog --category laptops
```

**Step 2 - Write the article**

Use the brief output to write the article. Follow these rules - they are enforced on publish:

- Include affiliate disclosure in the opening paragraph (within first 300 characters)
  - Example: *"Denne artikel indeholder affiliatelinks - vi tjener kommission uden ekstra omkostninger for dig."*
- Do not use forbidden superlatives: `bedste på markedet`, `nr. 1 valg`, `billigst i Danmark`, `absolut bedst`
- Cover every product listed in the brief
- Stay within the word count range in the brief (`writing_rules.minWords` - `writing_rules.maxWords`)

Save the article as a `.md` file (e.g. `articles/<run_id>.md`).

**Step 3 - Validate**

```bash
trendly validate --run <id> --article articles/<run_id>.md
```

Fix all `[ERROR]` items before publishing. `[WARN]` items are optional.

```
Validation: PASSED
Word count: 1043
No issues found. Ready to publish.
```

```
Validation: FAILED
Errors (2) - must fix before publishing:
  [ERROR] disclosure_missing: Missing affiliate disclosure in opening 300 characters
  [ERROR] superlative_found: Forbidden term found: "bedste på markedet"
```

**Step 4 - Publish**

```bash
# Save as draft (default - review in WP admin before going live)
trendly publish --run <id> --article articles/<run_id>.md

# Publish live immediately
trendly publish --run <id> --article articles/<run_id>.md --live
```

Always default to draft. Only use `--live` after reviewing the draft in WordPress.

---

## Agent workflow

With Augment or Claude, simply ask:

> "Generate an article for techblog"

The agent activates the `trendly-generate` skill and runs the full pipeline automatically:

1. Runs `trendly generate` to find the best gap and get a brief
2. Writes the article using the `article-generator` subagent prompt
3. Saves the article and runs `trendly validate`
4. Self-reviews (SEO, CRO, voice) using the `article-reviewer` subagent
5. Fixes any blockers and re-validates (max 2 cycles)
6. Publishes as WordPress draft with `trendly publish`

To go live, confirm explicitly after reviewing the draft in WordPress admin.

**Available skills** (in `.openclaw/skills/`):

| Skill | Trigger |
|-------|---------|
| `trendly-generate` | "generate an article for techblog" |
| `trendly-find-gap` | "what should I write next", "find a gap" |
| `trendly-publish` | "publish the article", "validate the article" |
| `trendly-runs` | "show runs", "what was published", "run history" |
| `trendly-setup` | "check setup", "test WP connection" |

---

## Compliance gates

These checks run on every `validate` and `publish` call. They cannot be skipped.

| Gate | Rule |
|------|------|
| `disclosure_missing` | Affiliate disclosure must appear in the first 300 characters |
| `superlative_found` | Forbidden phrases: `bedste på markedet`, `nr. 1 valg`, `billigst i Danmark`, `absolut bedst` |
| `word_count_low` | Article must meet the minimum word count for its type |
| `anchor_unresolved` | Every widget placement anchor must match an actual heading in the article |

Rules are configured in `config/compliance-rules.json`.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `category_exhausted` | All products in category already published | Choose a different category or wait for cooldown |
| `all_categories_exhausted` | Every category is exhausted or in cooldown | Add categories to `config/categories.json` |
| `disclosure_missing` | No affiliate disclosure in opening | Add disclosure phrase to first paragraph |
| `superlative_found` | Forbidden phrase used | Remove or rephrase |
| `anchor_unresolved` | Widget placement anchor heading not found | Use exact heading text from the article |
| `run_not_found` | Wrong run ID | Check with `trendly runs` |
| `WP 401` | Wrong credentials | Check app password in `.env` |
| `WP 404` | Wrong base URL | Check `WP_*_BASE_URL` in `.env` |

---

## Project layout

```
.openclaw/
  skills/             Agent skill definitions (one per workflow step)
  subagents/          Article generator and reviewer prompts
  taskflows/          Automated YAML pipelines (on-demand + daily cron)
config/
  categories.json     PriceRunner category mappings per site
  compliance-rules.json  Disclosure phrases and forbidden terms
  article-types.json  Word counts and CRO weights per article type
data/
  trendly.db          SQLite: runs, published products, category cooldowns
docs/
  INSTALL.md          Detailed installation steps
  USAGE.md            CLI reference and workflow details
prompts/agents/       Writing instructions per article type
src/
  cli/                CLI commands: generate, validate, publish, runs, setup
  services/           Core logic: brief, validation, publish gate, widgets
  store/              SQLite wrapper + migrations
  scraper/            PriceRunner API client
  types/              Zod schemas - single source of truth
```
