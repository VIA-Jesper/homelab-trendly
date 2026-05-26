---
name: trendly-generate
description: >
  Generate and publish a Trendly affiliate article for techblog or husforbegyndere.
  Activate when the user asks to "write an article", "generate content", "run trendly",
  "publish an article for [site]", or similar content generation requests.
triggers:
  - "write an article"
  - "generate content for"
  - "run trendly"
  - "publish article"
  - "trendly generate"
---

# Trendly Generate Skill

## When to activate

Activate this skill when the user wants to generate, write, or publish an affiliate article using Trendly.

## Workflow

Follow these steps in order. Do not skip any step.

### Step 1: Get brief

```bash
npm run cli -- generate --site <site> --json
```

Force a category if needed:

```bash
npm run cli -- generate --site techblog --category laptops --json
```

**Save the `run_id`** from the JSON output - you need it for every subsequent step.

### Step 2: Write the article

Use the `article-generator` subagent prompt (`.openclaw/subagents/article-generator.md`) and the `writingInstructions` from the brief output.

**Rules enforced server-side on publish - do not skip:**
- Affiliate disclosure in the opening paragraph (within first 300 chars)
- No forbidden superlatives ("bedste på markedet", "nr. 1 valg", etc.)
- Word count within `writing_rules.minWords`-`writing_rules.maxWords`
- All products from `brief.products` covered

Save the article to a `.md` file (e.g. `articles/<run_id>.md`).

### Step 3: Validate

```bash
npm run cli -- validate --run <run_id> --article articles/<run_id>.md
```

Fix ALL `[ERROR]` items before proceeding. `[WARN]` items are optional. Re-validate after fixes.

### Step 4: Review (self-review using article-reviewer subagent)

Apply the `article-reviewer` checklist (`.openclaw/subagents/article-reviewer.md`):
- **SEO**: category keyword in headings, compelling intro
- **CRO**: clear prices, disclosure not off-putting, clear verdict
- **Voice**: consistent tone, natural Danish, no ad-copy feel

If blockers found, revise and re-validate. Max 2 revision cycles.

### Step 5: Publish

```bash
# Save as draft (always default)
npm run cli -- publish --run <run_id> --article articles/<run_id>.md

# Go live (only when user explicitly confirms)
npm run cli -- publish --run <run_id> --article articles/<run_id>.md --live
```

## Sites

| Key | Description |
|-----|-------------|
| `techblog` | Danish tech reviews (laptops, phones, headphones, TVs) |
| `husforbegyndere` | Danish home/garden (coffee machines, robot vacuums, grills) |

## Related skills

- `trendly-find-gap` - get a brief without writing
- `trendly-publish` - validate and publish an existing article
- `trendly-runs` - view run history
