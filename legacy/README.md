# Legacy Archive

This folder contains files from the v1 implementation that have been superseded by the v2 agentic redesign.

Nothing here is deleted - it is preserved for reference and migration purposes.

## Archived Files and Their Replacements

### scripts/ -> src/cli/index.ts

| Legacy script | v2 replacement |
|---|---|
| `run-pipeline.mjs` | `trendly generate --site <key>` (CLI) |
| `mcp-generate.mjs` | `get_brief` MCP tool + write article |
| `mcp-publish.mjs` | `publish_article` MCP tool |
| `mcp-test.mjs` | `trendly setup` (CLI) |
| `validate-article.ts` | `trendly validate <run-id>` |
| `publish-article.mjs` | `trendly publish <run-id>` |
| `build-live-brief.ts` | `trendly find-gap --site <key>` |
| `find-pr-category.ts` | `src/services/category-discoverer.ts` |
| `seed.ts` | `src/store/migrations/001_init.sql` |
| `preview-server.ts` | not replaced (dev only) |
| `smoke-server.ts` | `trendly setup` (smoke test step) |
| `seo-generator.ts` | inline in publish-service.ts |
| `seo-validator.ts` | inline in validator.ts |
| All others | absorbed into services |

### prompts/ (generated artifacts)

The JSON and HTML files in `legacy/prompts/` were generated during v1 test runs.
They are preserved for reference when writing tests.

In v2, generated article state lives in SQLite (`data/trendly.db`, `runs` table).

### runs/

`legacy/runs/robotstovsugere/` contains the full output of a v1 test run for the
robotstovsugere (robot vacuum) category. Preserved for comparison testing.

### docs/reference/ (moved, not legacy)

`ARCHITECTURE.md`, `PRICERUNNER-SCRAPER-REFERENCE.md`, and `WIDGET-SYSTEM-REFERENCE.md`
were moved to `docs/reference/` and updated for v2.

## Active Files (NOT archived)

- `prompts/agents/` - active generator, reviewer, critiquer prompts
- `prompts/generate-article.md` - active article generation prompt
- `prompts/generate-article-task.md` - active task template
- `src/` - all source code (v2)
- `config/` - site and article-type config
