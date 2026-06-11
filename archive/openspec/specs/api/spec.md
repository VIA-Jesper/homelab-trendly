# API - Trendly REST Interface

The REST API runs on port 3000 (Fastify). The MCP server runs on port 3001 - see
`openspec/changes/mcp-article-pipeline/specs/mcp-interface/spec.md` for MCP tool definitions.

## Requirements

### REQ-API-001 - Generate Job
The API SHALL accept POST /generate with a JSON body containing either
a `category` string or a `productUrl` string (at least one required).
Response: HTTP 202 { job_id, brief }

### REQ-API-002 - Retrieve Brief
GET /generate/{job_id}/brief returns the stored brief or HTTP 404.

### REQ-API-003 - Publish Article
POST /generate/{job_id}/publish: inject placements → convert Markdown → affiliate links → publish to WordPress.
Response: { status, wp_post_id, url, site, warnings[] }

### REQ-API-004 - Job Status
GET /generate/{job_id}/status returns { job_id, status: pending|briefed|published|failed }

### REQ-API-005 - OpenAPI Spec
GET /openapi.json serves a valid OpenAPI 3.1 document.
GET /docs serves interactive Swagger UI.

### REQ-API-006 - Health Probe
GET /health returns { status: "ok", uptime: <seconds>, version: "1.0.0" }.
Used by Docker healthcheck, Kubernetes readiness probes, and hosted platforms.
Response is always HTTP 200 as long as the process is running.

### REQ-API-007 - MCP Discovery
GET /mcp-info returns { mcpPort, transport, endpoint, tools[] } describing the MCP server.
Allows clients to discover the MCP endpoint without reading configuration files.

## Scenarios

### Scenario: Happy-path generate
GIVEN a client sends POST /generate with { "category": "laptops" }
WHEN the handler processes the request
THEN HTTP 202 is returned with a job_id UUID and a populated brief object

### Scenario: Missing input
GIVEN a client sends POST /generate with an empty body
WHEN Zod validation runs
THEN HTTP 400 is returned with a validation error message

### Scenario: Unknown job
GIVEN a client sends GET /generate/nonexistent-id/brief
WHEN the job store is queried
THEN HTTP 404 is returned with { "error": "Job not found" }

### Scenario: Health check
GIVEN the process is running
WHEN a client sends GET /health
THEN HTTP 200 is returned with { status: "ok", uptime: <n>, version: "1.0.0" }

### Scenario: MCP discovery
GIVEN a client sends GET /mcp-info
WHEN the handler responds
THEN { mcpPort: 3001, transport: "streamable-http", endpoint: "/mcp", tools: ["get_brief", "validate_article", "publish_article"] } is returned
