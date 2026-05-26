# Trendly - Installation

## Prerequisites

- Node.js 20+
- A WordPress site with REST API enabled (per site)
- PriceRunner affiliate partner ID (per site)

## 1. Install dependencies

```bash
npm install
```

## 2. Configure environment

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# techblog
WP_TECHBLOG_USER=your-wp-username
WP_TECHBLOG_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_TECHBLOG_BASE_URL=https://your-techblog.dk
PR_TECHBLOG_PARTNER_ID=your-pricerunner-id

# husforbegyndere
WP_HUS_USER=your-wp-username
WP_HUS_PASS=xxxx xxxx xxxx xxxx xxxx xxxx
WP_HUS_URL=https://husforbegyndere.dk
PR_HUS_PARTNER_ID=your-pricerunner-id
```

**WordPress Application Password:** Go to WP Admin -> Users -> Your Profile -> Application Passwords. Create one named "Trendly". Use that value (spaces included) as the password.

## 3. Run setup check

```bash
npm run cli -- setup
```

This validates env vars, applies SQLite migrations (creates `data/trendly.db`), and tests WP connectivity for each site.

## 4. Migrate legacy data (upgrading from v1 only)

If you have existing `data/content-registry.json` or `data/published-log.json`:

```bash
npm run migrate
```

Imports v1 data into SQLite and renames old files to `.legacy`.

## 5. Optional: install CLI globally

```bash
npm link
trendly setup
```

Without `npm link`, prefix all commands with `npm run cli --`:

```bash
npm run cli -- generate --site techblog
```

## 6. Verify

```bash
npm run cli -- generate --site techblog --json
```

Should return a JSON brief with `run_id` and product data. If it returns `category_exhausted`, your product database may be empty - see `docs/USAGE.md` for seeding.
