# Danish Affiliate Content Pipeline

Automated pipeline for generating, reviewing, and publishing Danish affiliate articles from PriceRunner product data. Uses a multi-agent architecture (Generator + parallel Reviewers + Critiquer) to produce SEO- and CRO-optimized article JSON, validated before publishing to WordPress.

## Documentation

| Document | What it covers |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **Start here.** System map, all architectural decisions (ADRs), known issues, env vars |
| [`.agents/flows/article-pipeline/FLOW.md`](.agents/flows/article-pipeline/FLOW.md) | End-to-end pipeline flow — phases, agent models, orchestration rules, rollback |
| [`WIDGET-SYSTEM-REFERENCE.md`](WIDGET-SYSTEM-REFERENCE.md) | PriceRunner widget embed system, affiliate link insertion, placement algorithm |
| [`PRICERUNNER-SCRAPER-REFERENCE.md`](PRICERUNNER-SCRAPER-REFERENCE.md) | PriceRunner API client, product data shape, category traversal |
| [`docs/llm-optimization.md`](docs/llm-optimization.md) | Planned: llms.txt, Schema.org, EEAT signals, AI crawler config |

## Quick start

```powershell
# Install dependencies
npm install

# Preview an existing article
npx tsx scripts/preview-server.ts
# → http://localhost:3030/?slug=robotstovsugere-sample

# Validate an article
npx tsx scripts/validate-article.ts prompts/article-robotstovsugere-sample.json prompts/brief-robotstovsugere-sample.json

# Run the full pipeline (requires auggie CLI)
# See .agents/flows/article-pipeline/FLOW.md for orchestration steps
```

## MCP connection

The MCP server runs on port 3001 using the Streamable HTTP transport.

**Endpoint:** `POST http://<host>:3001/mcp`
**Transport:** `streamable-http`
**Client config:** see `mcp.json` at repo root

### Connection sequence

1. POST `initialize` to `/mcp` - capture `Mcp-Session-Id` from response header
2. Include `Mcp-Session-Id: <id>` in all subsequent requests
3. Call tools using `tools/call` method

### Available tools

| Tool | Description |
|------|-------------|
| `get_brief` | Fetches PriceRunner products and returns a brief + writing instructions + `job_id` |
| `validate_article` | Validates a Markdown article against its brief. Returns pass/fail, scores, issues |
| `publish_article` | Converts article to HTML, inserts affiliate widgets, publishes to WordPress |

### Hosted deployment

Replace `localhost` with your service hostname. A `/health` endpoint is available on port 3000 for readiness probes.

## Environment variables

See [`ARCHITECTURE.md`](ARCHITECTURE.md#environment-variables) for the full list. Minimum for local dev: none required (widgets fall back to Tailwind cards, WP publishing is disabled).

## Project layout

```
config/               Per-type article rules (word counts, CRO weights, AI-tells)
docs/                 Implementation notes and planned work
prompts/
  agents/             System prompts for Generator, Reviewers, Critiquer
  agents/generator-types/  Per-type writing instructions (one file per article type)
  article-*.json      Generated article output (dev/test)
  brief-*.json        Content briefs (input to generator)
runs/                 Per-run logs for retrospective analysis
scripts/              CLI tools: validate, preview, seed, smoke test
src/
  config/             Site configs (WP credentials, partner IDs via env vars)
  scraper/            PriceRunner API client
  services/           Core logic: brief-builder, widget-inserter, affiliate-linker, validator
  types/              Zod schemas — single source of truth for all data shapes
.agents/flows/        Agent orchestration flows (FLOW.md)
```
