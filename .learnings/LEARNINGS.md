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
**Problem:** Articles contained em dashes (—) which violate the no-em-dash rule.
**Prevention:** Generator prompt forbids them. Reviewer loop checks. Always verify.
