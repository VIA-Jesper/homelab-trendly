---
name: article-pipeline
description: >
  Generate, validate, multi-reviewer critique, and approve a Danish affiliate
  article JSON optimized for SEO, conversion, and natural Danish voice.
  Parameterized by $CATEGORY. Orchestrator is the only file writer.
when: >
  Use this flow when the user wants to produce a publish-ready affiliate article
  for a given product category, with iterative quality checks across SEO, CRO,
  and voice axes, a WordPress-style preview, and a retrospective that proposes
  improvements to the pipeline itself.
version: "3.0"
---

# Article Pipeline Flow (OpenClaw Edition)

## Security Model

Sub-agents spawned via `sessions_spawn` ALWAYS run in isolated sessions.
They produce TEXT ONLY - they cannot write files or call mutating tools.

YOU (the orchestrator) are the ONLY agent that writes files.
All sub-agent sessions are isolated (no `context: "fork"` unless transcript needed).

---

## Parameters

| Param | Required | Example | Notes |
|---|---|---|---|
| `$CATEGORY` | yes | `laptops`, `headphones`, `coffee-machines` | Slug-form, lowercase |
| `$ARTICLE_TYPE` | no | `deal`, `hero`, `single-product-review` | Overrides classifier. If omitted, brief's `articleType` is used. |
| `$REGENERATE` | no | `true` / `false` | Force Phase 1 even if article exists |
| `$MAX_QUALITY_ITER` | no | `3` (default) | Cap on Phase 3 review loops |

Derived paths:
- Brief: `prompts/brief-$CATEGORY-sample.json` (must exist)
- Article: `prompts/article-$CATEGORY-sample.json` (orchestrator writes)
- Type module: `prompts/agents/generator-types/$ARTICLE_TYPE.md` (orchestrator reads)
- Run log dir: `runs/$CATEGORY/$ISO_TIMESTAMP/` (orchestrator writes)

---

## Files in Scope

| File | Role |
|---|---|
| `prompts/brief-$CATEGORY-sample.json` | Input brief |
| `prompts/article-$CATEGORY-sample.json` | Article output |
| `prompts/agents/generator.md` | Generator base prompt |
| `prompts/agents/generator-types/$TYPE.md` | Type-specific writing instructions |
| `prompts/agents/critiquer.md` | Critiquer system prompt |
| `prompts/agents/reviewer-seo.md` | SEO reviewer prompt |
| `prompts/agents/reviewer-cro.md` | CRO reviewer prompt |
| `prompts/agents/reviewer-voice.md` | Danish voice reviewer prompt |
| `config/article-types.json` | Per-type numerics |
| `scripts/validate-article.ts` | Compliance + quality validator |
| `scripts/preview-server.ts` | Preview server |
| `runs/$CATEGORY/$TS/` | Per-run logs |

---

## PHASE 0 - Initialize Run

1. Confirm `$CATEGORY` is set. If not, ask the user.
2. Verify `prompts/brief-$CATEGORY-sample.json` exists. If not, build it via MCP `get_brief` first.
3. Create run dir: `runs/$CATEGORY/$(date -u +%Y-%m-%dT%H-%M-%S)/`.
4. Read brief → `$BRIEF`.
5. Determine `$ARTICLE_TYPE`:
   - If param explicitly provided → use it
   - Else → read `brief.articleType`
   - Final fallback → `"roundup"`
6. Read `prompts/agents/generator.md` → `$GENERATOR_BASE`.
7. Read `prompts/agents/generator-types/$ARTICLE_TYPE.md` → `$TYPE_MODULE`.
8. Print: `Run started for category=$CATEGORY, articleType=$ARTICLE_TYPE`.

---

## PHASE 1 - Generate

**Goal:** Produce a complete article JSON.
**Method:** Spawn a single `sessions_spawn` sub-agent with the assembled prompt.

### Sub-agent prompt body

```
$GENERATOR_BASE

---

## Type Instructions

$TYPE_MODULE

---

## Brief
$BRIEF
```

**Spawn:** `sessions_spawn` with the above prompt as `task`, `mode="run"`, `timeoutSeconds=300`.
**Collect:** Parse response as JSON → `$ARTICLE`. Strip code fences.
**YOU write:**
- `prompts/article-$CATEGORY-sample.json`
- `runs/$CATEGORY/$TS/01-generated.json`

**Abort if:** JSON parse fails twice. Save raw response to `runs/.../01-raw.txt`.

---

## PHASE 2 - Compliance Validation

**No agent.** Run locally:

```bash
npx tsx scripts/validate-article.ts prompts/article-$CATEGORY-sample.json prompts/brief-$CATEGORY-sample.json
```

Save stdout to `runs/$CATEGORY/$TS/02-validation.txt`.

- **PASS (exit 0)** → proceed to Phase 3
- **FAIL** → proceed to Phase 3 with validator output included

---

## PHASE 3 - Quality Review Loop

**Goal:** Reach quality thresholds on SEO, CRO, and voice axes.
**Pass criteria:** All three reviewers return `verdict: "pass"` AND compliance exit 0.
**Max iterations:** `$MAX_QUALITY_ITER` (default 3).

### 3a - Spawn three reviewers IN PARALLEL

Launch three `sessions_spawn` simultaneously (no `context` needed - isolated sessions):

**SEO reviewer prompt:**
```
[contents of prompts/agents/reviewer-seo.md]

## Article JSON
$ARTICLE_RAW

## Brief
$BRIEF
```

**CRO reviewer prompt:** (same pattern with `reviewer-cro.md`)
**Voice reviewer prompt:** (same pattern with `reviewer-voice.md`)

**Spawn:** Three `sessions_spawn` calls at once. Set `taskName` for each (e.g. `reviewer-seo`, `reviewer-cro`, `reviewer-voice`).

Wait for all three to return via `sessions_yield`. Save each as:
- `runs/$CATEGORY/$TS/03-iter$N-seo.json`
- `runs/$CATEGORY/$TS/03-iter$N-cro.json`
- `runs/$CATEGORY/$TS/03-iter$N-voice.json`

### 3b - Check pass criteria

If all three verdicts are `pass` AND Phase 2 compliance is exit 0 → proceed to Phase 4.

### 3c - Merge and apply critiques

Compose a single critiquer prompt:
```
[contents of prompts/agents/critiquer.md]

## Current article JSON
$ARTICLE_RAW

## Validator output
$VALIDATION_TEXT

## SEO critique
$SEO_JSON

## CRO critique
$CRO_JSON

## Voice critique
$VOICE_JSON

## Brief
$BRIEF
```

**Spawn:** `sessions_spawn` with above prompt, `timeoutSeconds=300`.
Collect revised JSON. **YOU write:**
- `prompts/article-$CATEGORY-sample.json`
- `runs/$CATEGORY/$TS/03-iter$N-revised.json`

Re-run Phase 2 and 3a. Loop until pass or `$N == $MAX_QUALITY_ITER`.

### 3d - On iteration limit

Print summary of remaining issues per axis. Ask user:
- `[Approve anyway]` - proceed to Phase 4
- `[More iterations]` - extend limit by 2
- `[Abort]` - stop

---

## PHASE 4 - Preview + Human Approval

1. Start preview server: `npx tsx scripts/preview-server.ts` (background).
2. Print: `Preview: http://localhost:3030`.
3. Print scores from latest validation.
4. Ask user:
   - `[Approve]` → Phase 5a
   - `[Reject]` → abort
   - Custom text → Phase 5b

---

## PHASE 5a - Finalize (on Approve)

1. Confirm `prompts/article-$CATEGORY-sample.json` is latest.
2. Copy to `runs/$CATEGORY/$TS/05-final.json`.
3. Print: `Article approved. Final: prompts/article-$CATEGORY-sample.json`.

---

## PHASE 5b - Apply User Critique

Spawn `sessions_spawn` with critiquer prompt + user critique. Collect revised JSON. Save. Loop back to Phase 2.

---

## PHASE 6 - Retrospective (optional)

Read all files in `runs/$CATEGORY/$TS/`. Identify recurring issues.
Write `runs/$CATEGORY/$TS/06-retro.json`.

---

## Flow Summary Table

| Phase | Agent(s) | Method | Output |
|---|---|---|---|
| 0 - Init | none | local | Run dir, $BRIEF |
| 1 - Generate | 1 sub-agent | `sessions_spawn` | `$ARTICLE` JSON |
| 2 - Validate | none | local script | exit code |
| 3a - Review | 3 sub-agents parallel | `sessions_spawn` ×3 | 3 critiques |
| 3c - Critique | 1 sub-agent | `sessions_spawn` | Revised article |
| 4 - Preview | preview-server | local | HTML at :3030 |
| 5a - Finalize | orchestrator | local | Saved JSON |
| 5b - User fix | 1 sub-agent | `sessions_spawn` | Revised article |
| 6 - Retro | orchestrator | local | Proposals |

---

## Known Limitations

- **Brief format**: All categories share the same brief schema.
- **Sub-agent timeout**: Generator and critiquer get 300s. Adjust if articles are complex.
- **Parallel reviewer cold start**: Three concurrent `sessions_spawn` calls may take 30-60s each to start. Subsequent iterations are faster.
- **JSON parse fragility**: Strip code fences and use lenient newline parsing.
