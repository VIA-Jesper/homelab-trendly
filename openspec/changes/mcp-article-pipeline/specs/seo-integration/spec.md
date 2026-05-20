# SEO Integration — RankMath Field Delivery

## ADDED Requirements

### Requirement: RankMath SEO metadata delivery
When publishing to WordPress, the system SHALL write SEO metadata to the post via the WP REST
API `meta` field using RankMath's known meta keys:
- `rank_math_title` — from `seo.title` if provided, else falls back to article H1
- `rank_math_description` — from `seo.description` if provided; no fallback (omitted if missing)
- `rank_math_focus_keyword` — from `seo.focus_keyword` if provided; omitted if missing

If RankMath is not installed on the target site, WordPress SHALL silently ignore the meta fields.
The system SHALL log a warning but SHALL NOT fail the publish request.

#### Scenario: Full SEO payload provided
- **WHEN** publish_article is called with seo.title, seo.description, and seo.focus_keyword
- **THEN** all three RankMath meta keys are included in the WP REST API post body

#### Scenario: Partial SEO payload
- **WHEN** publish_article is called with only seo.title provided
- **THEN** rank_math_title is set; rank_math_description and rank_math_focus_keyword are omitted

#### Scenario: No SEO payload
- **WHEN** publish_article is called without an seo object
- **THEN** rank_math_title falls back to the article H1; other SEO fields are omitted

#### Scenario: RankMath not installed
- **WHEN** WordPress does not have RankMath installed
- **THEN** publish succeeds; system logs warning "RankMath meta fields may not be applied"

---

### Requirement: Slug generation
The system SHALL set the WordPress post slug from `seo.slug` if provided.
If not provided, the system SHALL derive a slug by slugifying the article H1:
lowercase, spaces to hyphens, special characters removed, Danish characters transliterated
(æ→ae, ø→oe, å→aa).

#### Scenario: Slug provided
- **WHEN** publish_article is called with seo.slug = "bedste-laptops-2025"
- **THEN** WordPress post is created with slug "bedste-laptops-2025"

#### Scenario: Slug derived from H1
- **WHEN** publish_article is called without seo.slug and H1 is "Bedste Laptops 2025"
- **THEN** WordPress post slug is set to "bedste-laptops-2025"

#### Scenario: Danish characters in H1
- **WHEN** H1 contains "Bedste Høretelefoner"
- **THEN** slug is derived as "bedste-hoeretelefoner"

---

### Requirement: WordPress category resolution
The system SHALL resolve the article's WordPress category ID from the site config's `categoryMap`
using the brief's product category name. If no mapping exists, the site's default `categoryId`
SHALL be used. The agent SHALL never provide or reference WordPress category IDs directly.

#### Scenario: Category mapped
- **WHEN** brief category is "laptops" and site config categoryMap has { "laptops": 5 }
- **THEN** WordPress post is created with category ID 5

#### Scenario: Category not mapped
- **WHEN** brief category has no entry in categoryMap
- **THEN** WordPress post is created with the site's default categoryId
