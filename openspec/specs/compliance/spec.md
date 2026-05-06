# Compliance — Danish Marketing Act Rules

## Requirements

### REQ-COMP-001 — Disclosure
Every article SHALL contain a visible affiliate disclosure within the first 300 characters.
Accepted phrases (case-insensitive): "indeholder affiliatelinks", "vi tjener kommission",
"annonce", "reklame".

### REQ-COMP-002 — No False Superlatives
The article SHALL NOT use unsubstantiated superlatives such as "bedste på markedet",
"billigst i Danmark", "nr. 1 valg" unless backed by a cited source.

### REQ-COMP-003 — Widget Presence
Every product in the brief SHALL have a corresponding {{AFFILIATE_WIDGET_<ID>}} placeholder.

### REQ-COMP-004 — Confidence Score
The validator SHALL produce a confidence_score between 0 and 1.
Score < 0.7 triggers draft mode.

## Scenarios

### Scenario: Missing disclosure
GIVEN an article without a disclosure phrase in first 300 chars
WHEN the validator runs compliance checks
THEN issues contains "MISSING_DISCLOSURE"
AND confidence_score is reduced by 0.3

### Scenario: All checks pass
GIVEN a well-formed article with disclosure, no bad superlatives, all widgets
WHEN the validator runs
THEN issues is an empty array AND confidence_score is 1.0 AND publish_mode is "publish"
