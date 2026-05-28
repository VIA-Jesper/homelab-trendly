# TestFlow - Affiliate Article Generator

Autonomous pipeline for generating SEO-optimised Danish affiliate articles
and publishing them to WordPress with Yoast SEO metadata.

## Architecture

```
You (natural language) -> OpenClaw (reasoning + orchestration)
                            |
                    TypeScript Plugin (tool adapter + approval gate)
                            |
                    Python Tool Server :8000 (all I/O)
                            |
                    WordPress (draft created, you publish)
```

OpenClaw does ALL reasoning. Python does ALL I/O. You click Publish.

## Prerequisites

- Python 3.11+, Poetry 1.8+
- Node.js 18+ (for TypeScript plugin)
- WordPress site with REST API enabled, Yoast SEO plugin installed
- Yoast REST Bridge plugin installed (see `wp-plugin/`)
- OpenClaw installed

## Quick Start

```bash
# 1. Install Python dependencies
poetry install

# 2. Set up environment
cp .env.example .env
# Edit .env: add PriceRunner affiliate ID and WordPress app passwords

# 3. Configure your site
# Edit sites/site-one.yaml with your WordPress URL

# 4. Install Yoast REST Bridge on your WordPress site
# Upload wp-plugin/yoast-rest-bridge/ to wp-content/plugins/ and activate

# 5. Build and install the OpenClaw plugin
cd openclaw-plugin-testflow && npm install && cd ..
./scripts/build-plugin.sh

# 6. Start the tool server
./scripts/start.sh

# 7. Open OpenClaw in this directory and start writing:
# "write a best-of article about robot vacuums"
```

## CLI Usage (without OpenClaw)

```bash
# Pre-flight checks
python runner.py --site sites/site-one.yaml --check

# Dry run (fetch products + validate, no publish)
python runner.py --site sites/site-one.yaml --products "Roomba j9+" --dry-run

# Discover PriceRunner category IDs
python runner.py --discover "robotstovsuger"

# Generate OpenClaw prompt (paste into OpenClaw)
python runner.py --site sites/site-one.yaml --products "Roomba j9+"
```

## Article Types

| Type | Description | Min products |
|------|-------------|------|
| `best-of-list` | Ranked list for a category | 3 |
| `single-review` | Deep review of one product | 1 |
| `versus` | Head-to-head battle | 2 |
| `comparison` | Multi-product comparison | 3 |
| `buying-guide` | Educational guide + recommendations | 2 |

## Development

```bash
poetry run task test       # run all tests
poetry run task lint       # ruff lint
poetry run task fmt        # auto-format
poetry run task check      # lint + typecheck
poetry run task start      # start tool server with hot reload
poetry run task build-plugin  # rebuild TypeScript plugin
```

## Adding a New Site

1. Create `sites/my-new-site.yaml` with name, url, username
2. Add `WP_APP_PASSWORD_MY_NEW_SITE=xxxx xxxx xxxx xxxx xxxx xxxx` to `.env`
3. Install Yoast REST Bridge plugin on the new WordPress site
4. Run with `--site sites/my-new-site.yaml`

## Security Notes

- Never commit `.env` (covered by `.gitignore`)
- WordPress `testflow-bot` user should have `Editor` role only (not Admin)
- Pipeline ALWAYS creates drafts - never publishes live
- Human reviews and clicks Publish in WP Admin
- `testflow_create_draft` tool requires manual approval in OpenClaw chat
