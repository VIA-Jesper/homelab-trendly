#!/bin/bash
# Wrapper to set env vars before running the TypeScript script
export WP_HUS_URL="https://husforbegyndere.dk"
export WP_HUS_USER="vnisq8"
export WP_HUS_PASS="In11 CAkL 9jrz dQ5e gdpf BDK1"
export PR_HUS_PARTNER_ID="adrunner_dk_husforbegyndere"
export GITHUB_ACCESS_TOKEN=$(grep GITHUB_ACCESS_TOKEN /home/jhe/.openclaw/workspace-affiliate-marketing/.env | head -1 | cut -d= -f2)

cd /home/jhe/.openclaw/workspace-affiliate-marketing/github/homelab-trendly

# If post ID provided as 4th arg, update instead of create
if [ -n "$4" ]; then
  npx tsx scripts/update-article.mjs "$1" "$2" "$3" "$4"
else
  npx tsx scripts/publish-article.mjs "$1" "$2" "$3"
fi
