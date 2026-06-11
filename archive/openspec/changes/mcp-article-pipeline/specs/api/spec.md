# API - Delta Spec

## MODIFIED Requirements

### Requirement: Publish Article
POST /generate/{job_id}/publish response shape updated to match WordPress publisher output.

The endpoint SHALL accept the same body as the MCP publish_article tool (article, site, status,
placements, seo) and return `{ status, wp_post_id, url, site, warnings[] }`.

The REST endpoint is a developer/testing surface. The MCP tool is the production interface.

#### Scenario: Successful publish via REST
- **WHEN** POST /generate/{job_id}/publish is called with valid body
- **THEN** response is `{ status: "published", wp_post_id, url, site, warnings: [] }`

#### Scenario: REST and MCP publish produce identical results
- **WHEN** same payload is submitted via REST API and MCP tool
- **THEN** both call the same underlying wp-publisher service and return the same response shape

---

## ADDED Requirements

### Requirement: MCP spec endpoint
The Fastify server SHALL continue to serve `GET /openapi.json` and `GET /docs`.
An additional endpoint `GET /mcp-info` SHALL be added returning:
`{ mcpPort: 3001, transport: "streamable-http", endpoint: "/mcp", tools: ["get_brief", "publish_article"] }`

#### Scenario: MCP info endpoint
- **WHEN** GET /mcp-info is called
- **THEN** response describes the MCP server location and available tools
