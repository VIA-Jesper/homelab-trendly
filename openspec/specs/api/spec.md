# API — Trendly REST Interface

## Requirements

### REQ-API-001 — Generate Job
The API SHALL accept POST /generate with a JSON body containing either
a `category` string or a `productUrl` string (at least one required).
Response: HTTP 202 { job_id, brief }

### REQ-API-002 — Retrieve Brief
GET /generate/{job_id}/brief returns the stored brief or HTTP 404.

### REQ-API-003 — Publish Article
POST /generate/{job_id}/publish: validate → insert widgets → publish to WordPress.
Response: { status, wp_post_id, post_url }

### REQ-API-004 — Job Status
GET /generate/{job_id}/status returns { job_id, status: pending|briefed|published|failed }

### REQ-API-005 — OpenAPI Spec
GET /openapi.json serves a valid OpenAPI 3.1 document.
GET /docs serves interactive Swagger UI.

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
