# TestFlow - Affiliate Article Generator

## What this project does
Generates Danish affiliate marketing articles using PriceRunner product data,
publishes them as drafts to WordPress sites, and maintains content quality
through a structured review pipeline.

## How to use me (OpenClaw instructions)

### Before starting
1. Make sure `tool_server.py` is running: `./scripts/start.sh`
   If the server is unreachable, the `testflow_*` tools will fail immediately with a
   connection error. Tell the user to run `./scripts/start.sh` and stop.
2. Read `skills/affiliate-pipeline.md` - this is your complete instruction set
3. Read `sites/pricerunner-categories.yaml` - you need this to resolve category IDs

### Generating an article
Tell me what you want in natural language. Examples:
- "do a review of the Roomba j9+"
- "write a best-of article about robot vacuums"
- "compare Roomba j9+ vs Ecovacs Deebot X2"
- "skriv om de bedste kaffemaskiner"

I will read the skill document and call the tool server to run the pipeline.

### Tool server base URL
http://localhost:8000

### Key files
- `skills/affiliate-pipeline.md` - pipeline instructions and tool definitions
- `sites/pricerunner-categories.yaml` - category ID lookup table
- `sites/site-one.yaml` - primary test site config
- `affiliate/config.yaml` - affiliate rules (ref params, widget, disclosure)
- `templates/*.yaml` - article structure definitions (5 types)
