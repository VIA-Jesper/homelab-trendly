## Deployment Readiness — Gap Fixes

All tasks completed 2026-05-20.

- [x] GAP 1: Add `COPY prompts/` to Dockerfile runner stage — agent writing instructions now baked into image
- [x] GAP 2: Create `mcp.json` at repo root — MCP client config for Streamable HTTP transport on port 3001
- [x] GAP 3: Add `/health` endpoint to `src/server.ts` — returns `{ status, uptime, version }` for Docker healthcheck and K8s readiness probes
- [x] GAP 3: Add `healthcheck:` block to `docker-compose.yml` — uses `wget` (alpine-compatible), 30s interval, 15s start period
- [x] GAP 3: Fix `/mcp-info` tool list — added missing `validate_article`
- [x] GAP 4: `published-log.json` safe init — already resolved prior to this session (existsSync guard + try/catch in duplicate-guard.ts)
- [x] GAP 5: Add `COPY .agents/` to Dockerfile runner stage — orchestration flow baked into image
- [x] GAP 5: Add `COPY docs/`, `COPY openspec/`, `COPY *.md` to Dockerfile — dev and architecture docs baked in for agentic development
- [x] GAP 6: Add MCP connection section to `README.md` — endpoint, transport, connection sequence, tool table, hosted deployment note
- [x] GAP 7: Create `llms.txt` at repo root — machine-readable service description for AI crawlers and agents
