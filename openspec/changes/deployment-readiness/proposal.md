# Deployment Readiness — Proposal

**Date:** 2026-05-20

## Problem

Seven gaps prevented reliable deployment of the Trendly MCP server to hosted environments
(Hermes, OpenClaw, Railway, Render). The container image was missing runtime files, lacked
standard observability endpoints, and had no machine-readable client configuration.

## Solution

Fix all seven gaps in one session:

1. **Dockerfile** — bake `prompts/`, `.agents/`, `docs/`, `openspec/`, and root `*.md` files
   into the runner image. The container is now fully self-contained: no volume mounts required
   for core functionality. Volumes in docker-compose.yml still override for local dev.

2. **`mcp.json`** — standard MCP client config at repo root. Agent platforms and MCP clients
   can auto-discover the endpoint (`http://localhost:3001/mcp`, `streamable-http` transport)
   without reading documentation.

3. **`/health` endpoint** — Fastify route returning `{ status, uptime, version }`. Docker
   healthcheck, Kubernetes readiness probes, and hosted platform monitors all use this.

4. **Docker healthcheck** — `healthcheck:` block in `docker-compose.yml` using `wget` (available
   in `node:20-alpine`). 30s interval, 5s timeout, 3 retries, 15s start period.

5. **`/mcp-info` fix** — tool list now correctly includes `validate_article` (was missing).

6. **README MCP section** — full connection instructions: endpoint, transport, session ID flow,
   tool table, and hosted deployment note.

7. **`llms.txt`** — machine-readable service description at repo root for AI crawlers and agents
   discovering the service.

## Success Criteria (all met)

- Container image is self-contained (no volume dependency for core functionality)
- Agent platforms can auto-discover MCP endpoint via `mcp.json`
- Container orchestrators can probe liveness via `/health`
- README gives operators everything needed to connect an MCP client
- All runtime file I/O fails gracefully (pre-existing)
