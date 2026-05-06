# Publisher — Output Rules

## Overview
Phase 1: write final article and validation report to local disk for manual review.
Phase 2: publish to WordPress via REST API v2.

## Requirements

### REQ-PUB-001 — Output Directory
The file writer SHALL write to output/{job_id}/ relative to the project root.
The directory SHALL be created if it does not exist.

### REQ-PUB-002 — Article File
output/{job_id}/article.html SHALL contain the final HTML article
with all {{AFFILIATE_WIDGET_*}} placeholders replaced with rendered widget HTML.

### REQ-PUB-003 — Report File
output/{job_id}/report.json SHALL contain:
{ job_id, brief_id, confidence_score, publish_mode, issues[], category, savedAt }

### REQ-PUB-004 — Response
The file writer SHALL return { status: "saved", filePath: "output/{job_id}/article.html" }.

### REQ-PUB-005 — Phase 2 Upgrade Path
Phase 2 adds wp-publisher.ts with the same function signature as file-writer.ts.
The route handler swaps the import — no other changes needed.

## Scenarios

### Scenario: Article saved
GIVEN a valid article and job_id
WHEN the file writer is called
THEN output/{job_id}/article.html and report.json are written to disk
AND { status: "saved", filePath: "..." } is returned

### Scenario: Low confidence article
GIVEN confidence_score < 0.7
WHEN the file writer is called
THEN both files are still written (draft review is the point)
AND report.json contains publish_mode: "draft" and the full issues list
