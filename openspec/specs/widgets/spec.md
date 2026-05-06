# Widgets — Affiliate Widget Insertion Rules

## Requirements

### REQ-WIDGET-001 — Placeholder Format
Placeholders SHALL follow the exact regex: \{\{AFFILIATE_WIDGET_([A-Z0-9_]+)\}\}

### REQ-WIDGET-002 — Widget HTML Structure
Each rendered widget SHALL be a <div class="trendly-affiliate-widget"> containing:
product name, current price in DKK, retailer name, and a CTA link.

### REQ-WIDGET-003 — Missing Products
If a placeholder references an unknown product ID, replace with empty string and
log a warning (no throw).

### REQ-WIDGET-004 — Phase Boundary
Phase 1: widget HTML built from brief product data.
Phase 2: widgets fetched from real affiliate network API.

## Scenarios

### Scenario: Valid placeholder
GIVEN article contains {{AFFILIATE_WIDGET_LAPTOP_001}}
AND the brief contains a product with id LAPTOP_001
WHEN the widget inserter processes the article
THEN the placeholder is replaced with a <div class="trendly-affiliate-widget"> block

### Scenario: Unknown product id
GIVEN article contains {{AFFILIATE_WIDGET_UNKNOWN_999}}
AND the brief does NOT contain that product
WHEN the widget inserter processes the article
THEN the placeholder is replaced with empty string and no error is thrown
