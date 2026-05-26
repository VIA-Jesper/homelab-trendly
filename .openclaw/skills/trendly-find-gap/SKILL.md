---
name: trendly-find-gap
description: >
  Find the best content gap for a Trendly site and generate a brief.
  Activate when the user asks "what should I write next", "find a gap",
  "what categories are available", or wants a brief without writing yet.
triggers:
  - "find a gap"
  - "what should I write"
  - "get a brief"
  - "trendly find-gap"
  - "what categories"
---

# Trendly Find Gap

Discovers the best unwritten category for a site and generates a content brief.
Does NOT write the article - just produces the brief and run_id.

## Command

```bash
npm run cli -- generate --site <site> --json
```

Or with a forced category:

```bash
npm run cli -- generate --site <site> --category <slug> --json
```

## Sites

| Key | Description |
|-----|-------------|
| `techblog` | Danish tech reviews (laptops, phones, headphones, TVs) |
| `husforbegyndere` | Danish home/garden (coffee machines, robot vacuums, grills) |

## What the output means

```json
{
  "run_id": 42,
  "brief": {
    "category": "laptops",
    "articleType": "comparison",
    "articleHook": "...",
    "products": [...],
    "writing_rules": { "minWords": 800, "maxWords": 1400, "tone": "analytical" },
    "compliance": { "requireDisclosure": true, "disclosurePhrases": [...] }
  },
  "writingInstructions": "..."
}
```

**Save the `run_id`** - you need it to validate and publish the article.

## After getting the brief

Options:
- Pass the brief to `article-generator` subagent to write the article now
- Share the brief with the user so they can write it manually
- Run `trendly generate` skill to do the full write + review + publish flow
