# Publisher - Delta Spec

## REMOVED Requirements

### Requirement: Output Directory
**Reason:** Phase 1 file-writer replaced by WordPress REST API publisher in Phase 2.
**Migration:** Articles are published directly to WordPress. No local file output.

### Requirement: Article File
**Reason:** Replaced by WordPress REST API publishing.
**Migration:** Final HTML is POST-ed to the WP REST API `/wp-json/wp/v2/posts` endpoint.

### Requirement: Report File
**Reason:** Report replaced by structured publish response and MCP tool return value.
**Migration:** Confidence score and issues are available in the MCP publish_article response.

### Requirement: Response
**Reason:** Response shape changed to include WordPress post metadata.
**Migration:** Response is now `{ status, wp_post_id, url, site, warnings[] }`.

---

## ADDED Requirements

### Requirement: WordPress REST API publishing
The system SHALL publish articles to WordPress using the WP REST API v2 at
`{wp_base_url}/wp-json/wp/v2/posts`. Authentication SHALL use HTTP Basic auth with
Application Password credentials loaded from environment variables
`WP_{SITE_KEY_UPPER}_USER` and `WP_{SITE_KEY_UPPER}_APP_PASSWORD`.

The POST body SHALL include: `title`, `content` (final HTML), `status`, `slug`, `categories`,
`meta` (SEO fields), and `featured_media` if a featured image product ID is provided.

On non-2xx response, the system SHALL retry with exponential backoff (same pattern as
pricerunner-client.ts). After max retries, the job SHALL be marked `failed`.

#### Scenario: Successful WordPress publish
- **WHEN** publish_article is called with valid inputs and WP credentials are correct
- **THEN** system POSTs to WP REST API and returns `{ status: "published", wp_post_id, url, site }`

#### Scenario: WordPress auth failure
- **WHEN** WP credentials are invalid
- **THEN** system returns error `{ error: "wp_auth_failed", site }` without retrying

#### Scenario: WordPress server error
- **WHEN** WP REST API returns 5xx
- **THEN** system retries with exponential backoff; after max retries returns `{ error: "wp_publish_failed" }`

---

### Requirement: Phase 1 file-writer preserved
The existing `file-writer.ts` SHALL remain in place and continue to function.
The route handler SHALL be updated to use `wp-publisher.ts` via import swap (per REQ-PUB-005).
Rollback is achieved by reverting the import.

#### Scenario: Rollback to file writer
- **WHEN** wp-publisher.ts import is reverted to file-writer.ts
- **THEN** system writes articles to disk as before with no other code changes required
