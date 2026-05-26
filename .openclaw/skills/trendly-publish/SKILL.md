---
name: trendly-publish
description: >
  Validate and publish a written Trendly article to WordPress.
  Activate when the user has a finished article and wants to validate,
  publish, or save as draft. Also handles "is it ready to publish?".
triggers:
  - "publish the article"
  - "save as draft"
  - "validate the article"
  - "is it ready to publish"
  - "trendly publish"
  - "trendly validate"
---

# Trendly Publish Skill

Validates an article against its brief, then publishes to WordPress.
The hard gate always fires server-side - disclosure and superlative checks cannot be skipped.

## Step 1: Validate

Always validate before publishing. Save the article to a file first.

```bash
npm run cli -- validate --run <run_id> --article <path/to/article.md>
```

### Interpreting validate output

**PASSED** - ready to publish:
```
Validation: PASSED
Word count: 1043
No issues found. Ready to publish.
```

**FAILED** - must fix errors:
```
Validation: FAILED
Errors (2) - must fix before publishing:
  [ERROR] disclosure_missing: Missing affiliate disclosure in opening 300 characters
  [ERROR] superlative_found: Forbidden term found: "bedste på markedet"
```

Fix ALL `[ERROR]` items before proceeding. `[WARN]` items are optional to fix.

## Step 2: Publish

After validation passes:

```bash
# Save as draft (safe default - review in WP admin before going live)
npm run cli -- publish --run <run_id> --article <path/to/article.md>

# Publish live immediately
npm run cli -- publish --run <run_id> --article <path/to/article.md> --live
```

**Always default to draft** unless the user explicitly asks to go live.

### Interpreting publish output

**Success:**
```
Status:   DRAFT
WP Post:  12345
URL:      https://techblog.dk/?p=12345
```

**Rejected by gate:**
```
REJECTED - hard gate failed:
  [GATE] disclosure_missing: Missing affiliate disclosure in opening 300 characters
```

This means the article failed the server-side compliance check. Fix the issue and re-validate.

## Common errors and fixes

| Error | Fix |
|-------|-----|
| `disclosure_missing` | Add "Denne artikel indeholder affiliatelinks" to first paragraph |
| `superlative_found: "bedste på markedet"` | Remove or rephrase the forbidden term |
| `word_count_low` | Article is too short - expand sections |
| `anchor_unresolved` | A placement anchor refers to a heading that doesn't exist |
| `run_not_found` | Wrong run_id - check with `trendly runs` |
