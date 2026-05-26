---
name: trendly-setup
description: >
  Set up Trendly for a new environment or verify an existing setup.
  Activate when the user asks about "setup", "configure trendly", "check env",
  "is trendly ready", or first-time setup questions.
triggers:
  - "setup trendly"
  - "configure trendly"
  - "check trendly env"
  - "trendly setup"
  - "is trendly ready"
---

# Trendly Setup Skill

## When to activate

Activate when the user wants to set up, verify, or troubleshoot Trendly's environment.

## Setup steps

### 1. Check environment variables

Required for each site:

**techblog:**
```
WP_TECHBLOG_USER=           # WordPress application username
WP_TECHBLOG_APP_PASSWORD=   # WordPress application password (not login password)
WP_TECHBLOG_BASE_URL=       # e.g. https://mytechblog.dk
PR_TECHBLOG_PARTNER_ID=     # PriceRunner affiliate partner ID
```

**husforbegyndere:**
```
WP_HUS_USER=
WP_HUS_PASS=
WP_HUS_URL=                 # e.g. https://husforbegyndere.dk
PR_HUS_PARTNER_ID=
```

Store these in `.env` (never commit this file - it is in .gitignore).

### 2. Run setup check

```bash
npm run cli -- setup
# or after npm link:
trendly setup
```

This will:
- Apply SQLite migrations (creates `data/trendly.db`)
- Check all env vars per site
- Test WordPress REST API connectivity
- Report any missing or broken configuration

### 3. Migrate legacy data (if upgrading from v1)

If you have existing `data/content-registry.json` or `data/published-log.json`:

```bash
npm run migrate
```

This imports v1 JSON data into SQLite and renames the old files to `.legacy`.

### 4. Test a dry run

Generate a brief without publishing:

```bash
npm run cli -- generate --site techblog --json
```

This creates a run in SQLite and returns the brief. Check that products are returned and the run_id is valid.

## WordPress Application Password

Go to: WordPress Admin -> Users -> Your Profile -> Application Passwords
Create a new application password named "Trendly". Use this as `WP_*_APP_PASSWORD`.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `WP connectivity: HTTP 401` | Wrong username or app password |
| `WP connectivity: HTTP 404` | Wrong base URL or REST API disabled |
| `category_exhausted` | All products in this category already published. Try a different category or wait. |
| `all_categories_exhausted` | All configured categories exhausted. Add new PriceRunner categories to `config/categories.json`. |
