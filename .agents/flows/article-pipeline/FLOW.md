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
version: "2.0"
---

# Article Pipeline Flow

## Security Model

Sub-agents spawned via ACP (`auggie --acp`) ALWAYS run in **ask mode**.
They produce TEXT ONLY - they cannot call `save-file`, `str-replace-editor`,
`launch-process`, or any mutating tool.

YOU (the orchestrator) are the ONLY agent that writes files.
All ACP sessions use `"mcpServers": []` explicitly.

---

## Parameters

| Param | Required | Example | Notes |
|---|---|---|---|
| `$CATEGORY` | yes | `laptops`, `headphones`, `coffee-machines` | Slug-form, lowercase |
| `$ARTICLE_TYPE` | no | `deal`, `hero`, `single-product-review` | Overrides classifier. If omitted, brief's `articleType` is used (set by classifier). |
| `$REGENERATE` | no | `true` / `false` | Force Phase 1 even if article exists |
| `$MAX_QUALITY_ITER` | no | `3` (default) | Cap on Phase 3 review loops |

Derived paths:
- Brief: `prompts/brief-$CATEGORY-sample.json` (must exist)
- Article: `prompts/article-$CATEGORY-sample.json` (orchestrator writes)
- Type module: `prompts/agents/generator-types/$ARTICLE_TYPE.md` (orchestrator reads and concatenates)
- Run log dir: `runs/$CATEGORY/$ISO_TIMESTAMP/` (orchestrator writes)

---

## Files in Scope

| File | Role |
|---|---|
| `prompts/brief-$CATEGORY-sample.json` | Input brief (includes `articleType` from classifier) |
| `prompts/article-$CATEGORY-sample.json` | Article output (includes `articleType` field) |
| `prompts/agents/generator.md` | Generator base prompt (universal rules) |
| `prompts/agents/generator-types/$TYPE.md` | Type-specific writing instructions (concatenated in Phase 1) |
| `prompts/agents/critiquer.md` | Critiquer system prompt (type-aware) |
| `prompts/agents/reviewer-seo.md` | SEO reviewer prompt (type-aware, Phase 3) |
| `prompts/agents/reviewer-cro.md` | CRO reviewer prompt (type-aware, Phase 3) |
| `prompts/agents/reviewer-voice.md` | Danish voice reviewer prompt (type-aware, Phase 3) |
| `config/article-types.json` | Per-type numerics: word counts, AI tells, CRO weights |
| `scripts/validate-article.ts` | Compliance + quality validator (reads type from article JSON) |
| `scripts/preview-server.ts` | Preview server (Phase 4) |
| `runs/$CATEGORY/$TS/` | Per-run logs for retrospective (Phase 6) |

---

## PHASE 0 - Initialize Run

1. Confirm `$CATEGORY` is set. If not, ask the user.
2. Verify `prompts/brief-$CATEGORY-sample.json` exists. If not, abort with a clear error.
3. Create run dir: `runs/$CATEGORY/$(Get-Date -Format yyyy-MM-ddTHH-mm-ss)/`.
4. Read brief → `$BRIEF`.
5. Determine `$ARTICLE_TYPE`:
   - If param explicitly provided by user → use it (override)
   - Else → read `brief.articleType` (set by classifier in `brief-builder.ts`)
   - Final fallback → `"roundup"`
6. Read `prompts/agents/generator.md` → `$GENERATOR_BASE`.
7. Read `prompts/agents/generator-types/$ARTICLE_TYPE.md` → `$TYPE_MODULE`.
8. Print: `Run $TS started for category=$CATEGORY, articleType=$ARTICLE_TYPE`.

---

## PHASE 1 - Generate (skip if article exists and `$REGENERATE != true`)

**Goal:** Produce a complete article JSON conforming to the output schema. The generator prompt is assembled from the base + type module.
**Launch:** `auggie --acp --model opus4.6`

### ACP session/prompt body (composed by orchestrator)

```
$GENERATOR_BASE

---

## Type Instructions

$TYPE_MODULE

---

## Brief
$BRIEF
```

The orchestrator concatenates `$GENERATOR_BASE` + `$TYPE_MODULE` + the brief. The type module overrides structural defaults in the base prompt. The generator must copy `articleType` from the brief into the output JSON.

**Collect:** Parse response as JSON -> `$ARTICLE`. Strip code fences if present.
**YOU write:**
- `prompts/article-$CATEGORY-sample.json` (the live article)
- `runs/$CATEGORY/$TS/01-generated.json` (snapshot for retrospective)

**Abort if:** JSON parse fails twice. Save raw response to `runs/.../01-raw.txt` and show user.

---

## PHASE 2 - Compliance Validation

**No agent.** YOU run:

```powershell
npx tsx scripts/validate-article.ts prompts/article-$CATEGORY-sample.json prompts/brief-$CATEGORY-sample.json
```

Save stdout to `runs/$CATEGORY/$TS/02-validation.txt`. Capture exit code.

- **PASS (exit 0)** -> proceed to Phase 3
- **FAIL** -> proceed to Phase 3 with validator output included in the critique bundle

---

## PHASE 3 - Quality Review Loop (parallel reviewers)

**Goal:** Reach quality thresholds on SEO, CRO, and voice axes.
**Pass criteria:** All three reviewers return `verdict: "pass"` AND compliance exit 0.
**Max iterations:** `$MAX_QUALITY_ITER` (default 3).

### 3a - Spawn three reviewers IN PARALLEL

Launch three `auggie --acp --model sonnet4.6` processes simultaneously, one per reviewer.
Each session gets:
```
[contents of prompts/agents/reviewer-{seo|cro|voice}.md]

## Article JSON
$ARTICLE_RAW

## Brief
$BRIEF
```

Wait for all three to return. Save each as:
- `runs/$CATEGORY/$TS/03-iter$N-seo.json`
- `runs/$CATEGORY/$TS/03-iter$N-cro.json`
- `runs/$CATEGORY/$TS/03-iter$N-voice.json`

### 3b - Check pass criteria

If all three verdicts are `pass` AND Phase 2 compliance is exit 0 -> proceed to Phase 4.

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

Launch `auggie --acp --model sonnet4.6`. Collect revised JSON.
**YOU write:**
- `prompts/article-$CATEGORY-sample.json`
- `runs/$CATEGORY/$TS/03-iter$N-revised.json`

Re-run Phase 2 (compliance) and Phase 3a (parallel reviewers).
Loop until pass or `$N == $MAX_QUALITY_ITER`.

### 3d - On iteration limit

Print a summary table of remaining issues per axis. Ask user:
- `[Approve anyway]` - proceed to Phase 4
- `[More iterations]` - extend limit by 2
- `[Abort]` - stop

---

## PHASE 4 - Preview + Human Approval

1. Start preview server in background: `npx tsx scripts/preview-server.ts`.
2. Print: `Preview ready at http://localhost:3030 (refresh between iterations)`.
3. Print iteration summary table:
   ```
   Words: X | Paragraphs: Y | Placements: Z
   SEO: 92/100 (pass) | CRO: 88/100 (pass) | Voice: 85/100 (pass)
   ```
4. Ask user via `ask-user`:
   - `[Approve]` - go to Phase 5
   - `[Reject]` - abort
   - Custom text - treat as user critique, go to Phase 5b

---

## PHASE 5a - Finalize (on Approve)

1. Confirm `prompts/article-$CATEGORY-sample.json` is the latest revision.
2. Copy to `runs/$CATEGORY/$TS/05-final.json`.
3. Stop preview server.
4. Print: `Article approved. Final: prompts/article-$CATEGORY-sample.json | Log: runs/$CATEGORY/$TS/`.
5. Proceed to Phase 6 (retrospective) - optional, ask user first.

---

## PHASE 5b - Apply User Critique

Launch `auggie --acp --model sonnet4.6` with critiquer prompt:
```
[contents of prompts/agents/critiquer.md]

## Current article JSON
$ARTICLE_RAW

## User critique
$USER_TEXT

## Brief
$BRIEF
```

Collect revised JSON. Save to live file + `runs/.../04-user-critique-$N.json`.
Loop back to Phase 2.

---

## PHASE 6 - Retrospective (optional)

**Goal:** Improve the pipeline itself based on what kept failing.

### 6a - Single-run analysis

Read all files in `runs/$CATEGORY/$TS/`. Identify:
- Validator errors that took 2+ iterations to fix
- Critique issues that appeared in 2+ iterations of the same axis
- AI tells found by voice reviewer that survived past iteration 1

Write findings to `runs/$CATEGORY/$TS/06-retro.json`:
```
{
  "recurring_issues": [
    { "axis": "voice", "issue": "...", "iterations_seen": [1, 2] }
  ],
  "proposed_changes": [
    { "file": "prompts/generate-article.md", "change": "...", "rationale": "..." }
  ]
}
```

### 6b - Cross-run pattern detection (auto-apply rules)

Scan `runs/$CATEGORY/*/06-retro.json` across the last 5 completed runs.
For each `proposed_changes` entry, count how many runs proposed it.

- **3+ runs propose same change** -> AUTO-APPLY: edit the target file, save before/after diff to `runs/$CATEGORY/$TS/06-applied.md`, ask user only for confirmation banner
- **2 runs** -> propose only: write a proposal to `.agents/flows/article-pipeline/proposals/$TS.md`
- **1 run** -> log only, no proposal

### 6c - Present to user

```
Retrospective complete.
Auto-applied: $N changes (see runs/$CATEGORY/$TS/06-applied.md)
Proposed: $M changes (see .agents/flows/article-pipeline/proposals/$TS.md)
```

---

## Flow Summary Table

| Phase | Agent(s) | Model | Mode | Output |
|---|---|---|---|---|
| 0 - Init | none | - | - | Run dir, $BRIEF, $RULES |
| 1 - Generate | 1 ACP | opus4.6 | ask | `$ARTICLE` JSON |
| 2 - Validate | none | - | - | exit code + `$VALIDATION` |
| 3a - Review | 3 ACP parallel | sonnet4.6 | ask | 3 critique JSONs |
| 3c - Critique merge | 1 ACP | sonnet4.6 | ask | Revised `$ARTICLE` |
| 4 - Preview | preview-server | - | interactive | HTML at :3030 |
| 5a - Finalize | orchestrator | - | write | Saved + logged JSON |
| 5b - User critique | 1 ACP | sonnet4.6 | ask | Revised `$ARTICLE` |
| 6 - Retrospective | orchestrator | - | analyze | Proposals + auto-applies |

---

## Known Limitations

- **Brief format**: All categories must share the same brief schema. New categories require manual brief creation for now.
- **Auto-apply scope**: Only edits prompt markdown and validator config. Does NOT auto-edit code in `scripts/`.
- **Cross-run analysis**: Naively counts identical `proposed_changes.change` strings. Use canonical wording in proposals.
- **JSON parse fragility**: Strip code fences and use lenient newline parsing (mirror `validate-article.ts` loader).
- **Parallel reviewer cold start**: Three concurrent `auggie` processes load MCP plugins each - first iteration is slow (~30-60s per process). Cache warm if running multiple categories in sequence.

---

## Rollback

The orchestrator writes only:
- `prompts/article-$CATEGORY-sample.json` (live article)
- `runs/$CATEGORY/$TS/*` (logs)
- Prompt files in `prompts/agents/*` (only during Phase 6b auto-apply)

To roll back a run:
```powershell
git checkout -- prompts/article-$CATEGORY-sample.json prompts/agents/
Remove-Item -Recurse runs/$CATEGORY/$TS
```

Kill lingering preview server: `Get-NetTCPConnection -LocalPort 3030 | Stop-Process -Id $_.OwningProcess`.
