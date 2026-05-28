---
name: trendly-runs
description: >
  View Trendly run history - list recent runs or inspect a specific run.
  Activate when the user asks "show runs", "what was published", "run history",
  "show me run 42", or wants to check the status of a previous generation.
triggers:
  - "show runs"
  - "run history"
  - "what was published"
  - "trendly runs"
  - "show run"
  - "run status"
---

# Trendly Runs Skill

Lists or inspects article generation runs stored in SQLite.

## List recent runs

```bash
npm run cli -- runs
```

Filter by site or status:

```bash
npm run cli -- runs --site techblog
npm run cli -- runs --site husforbegyndere --status published
npm run cli -- runs --limit 10
```

### Status values

| Status | Meaning |
|--------|---------|
| `briefed` | Brief generated, article not yet written |
| `generated` | Article written and validated |
| `publishing` | Currently posting to WordPress |
| `published` | Live on WordPress |
| `needs_review` | Validation failed - needs fixing |
| `failed` | Error during publish |

## Inspect a specific run

```bash
npm run cli -- runs show <run_id>
```

Shows full details: brief summary, validation result, WP URL, any errors.

## JSON output (for scripting)

```bash
npm run cli -- runs --json
npm run cli -- runs show 42 --json
```

## Common uses

**Find the run_id for an article you need to re-publish:**
```bash
npm run cli -- runs --site techblog --status needs_review
```

**Check what was published today:**
```bash
npm run cli -- runs --status published --limit 5
```

**Debug a failed run:**
```bash
npm run cli -- runs show <run_id>
# Look at the error field and validation section
```
