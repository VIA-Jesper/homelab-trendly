# Trendly - Usage

## Quick reference

```bash
trendly setup                                    # check env + DB + WP connectivity
trendly generate --site <site>                   # find gap + generate brief
trendly generate --site <site> --category <slug> # force category
trendly validate --run <id> --article <file>     # validate article against brief
trendly publish  --run <id> --article <file>     # save as WordPress draft
trendly publish  --run <id> --article <file> --live  # publish live
trendly runs                                     # list recent runs
trendly runs --site techblog --status published  # filter
trendly runs show <id>                           # run details + validation result
```

Add `--json` to any command for machine-readable output.

---

## Manual workflow (with agent)

### 1. Generate a brief

```bash
trendly generate --site techblog
```

Note the `Run ID` printed. This ties the brief, article, and publish together.

### 2. Write the article

Give the brief to your agent (Augment/Claude). The agent follows the `trendly-generate` skill and `article-generator` subagent instructions.

Key rules (enforced on publish):
- Affiliate disclosure in opening paragraph
- No forbidden superlatives
- Word count within range
- Every product from the brief mentioned

### 3. Validate

```bash
trendly validate --run <id> --article article.md
```

Fix any `[ERROR]` items (not warnings) before publishing.

### 4. Publish

```bash
trendly publish --run <id> --article article.md        # draft
trendly publish --run <id> --article article.md --live # live
```

---

## Agent-driven workflow

With the agent (Augment/Claude), simply ask:

> "Generate an article for techblog"

The agent activates the `trendly-generate` skill, runs the CLI commands, writes the article, self-reviews, and publishes as draft.

To go live, confirm explicitly after reviewing the draft in WordPress.

---

## Cron automation

Add to crontab for daily autonomous runs (runs both sites, publishes live):

```cron
0 8 * * 1-5  cd /path/to/trendly && node dist/cli/index.js generate --site techblog --json | node dist/cli/publish-from-brief.js
```

Or use the OpenClaw taskflow `daily-autonomous-run.yaml` if running OpenClaw.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `category_exhausted` | All products in category already published | Choose a different category or wait |
| `all_categories_exhausted` | All categories exhausted | Add categories to `config/categories.json` |
| `disclosure_missing` | No affiliate disclosure in opening | Add "Denne artikel indeholder affiliatelinks" to first paragraph |
| `superlative_found` | Forbidden phrase used | Remove or rephrase |
| `anchor_unresolved` | Placement anchor heading not found | Use exact heading text from article |
| `run_not_found` | Wrong run ID | Check with `trendly runs` |
| `WP: 401` | Wrong credentials | Check WP app password in `.env` |
| `WP: 404` | Wrong base URL | Check `WP_*_BASE_URL` in `.env` |
