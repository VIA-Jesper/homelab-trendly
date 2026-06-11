# Learnings

## 2026-05-24: Partner ID not auto-appended during manual publish
**Problem:** When publishing articles manually (without the full trendly pipeline), the ?partnerId= parameter was not appended to PriceRunner URLs.
**Root cause:** The husforbegyndere site config didn't exist in sites.ts.
**Fix:** Added husforbegyndere entry to SITE_CONFIGS with PR_HUS_PARTNER_ID env var.
**Prevention:** Always verify rendered HTML contains partnerId= before publishing.

## 2026-05-24: Year in article title/hook was wrong
**Problem:** build-live-brief.ts generated hooks with year 2025.
**Fix:** Added dynamic year replacement using currentDate in brief.

## 2026-05-24: Em dashes in generated articles
**Problem:** Articles contained em dashes (-) which violate the no-em-dash rule.
**Prevention:** Generator prompt forbids them. Reviewer loop checks. Always verify.

## 2026-05-24: MCP publish flow works but content quality matters
**Problem:** MCP publish_article handles widgets+partner IDs well, but article content was poor because I used a basic template instead of the writingInstructions from get_brief.
**Lesson:** The get_brief tool returns writingInstructions (generator prompt + type module). Use those to write the article, don't use a template.
**Best result:** Post 433 (Dreame X50 Ultra) - written manually with proper content, then published via WP-CLI with partner IDs added retroactively. Better than MCP-published posts 442/444/445.
**Hybrid approach that works:**
1. get_brief via MCP → get products + writingInstructions
2. Write article properly using the instructions (not a template)
3. validate_article via MCP → check compliance
4. Run 3 reviewers (SEO/CRO/Voice) inline
5. publish_article via MCP → widgets + partner IDs + WP publish
