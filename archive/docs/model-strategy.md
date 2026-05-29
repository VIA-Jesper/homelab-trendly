# Model Strategy - Autonomous Content Pipeline

_Last updated: 2026-05-26_

## Context

Notes from architectural discussion about building an autonomous, scheduled Danish affiliate
content pipeline. The goal is agentic generation, self-review, and publishing to WordPress
with no human in the loop (after initial trust period).

---

## Available Model Sources

### OpenCode Go ($10/month, $5 first month)
- DeepSeek V4 Pro
- DeepSeek V4 Flash
- Kimi K2.6
- Qwen3.6 Plus
- Qwen3.5 Plus
- MiMo-V2.5-Pro
- MiniMax M2.7
- GLM-5.1

### OpenRouter Free Tier (notable models)
- **OpenAI gpt-oss-120b** - 120B MoE, reasoning + tool use, OpenAI quality
- **Owl Alpha** - agentic-first, explicitly compatible with Claude Code / OpenClaw
- **NVIDIA Nemotron 3 Super** - 120B MoE (12B active), 1M context, multi-agent design
- **Google Gemma 4 31B** - 140+ language support (good for Danish), 256K context, thinking mode
- **DeepSeek V4 Flash** - 1M context, fast, good for cheap/scout tasks
- **Arcee Trinity Large Thinking** - 262K context, reasoning, good for critique
- **MiniMax M2.5** - 205K context, agentic workflow training

### Claude SDK Credits (available ~June 15, 2026)
- Claude Sonnet (best Danish prose, strongest instruction following)
- Claude Haiku (cheap, good for structured review/critique)
- Claude Opus (highest capability, use for generation when budget allows)

---

## Recommended Multi-Model Assignment

Each pipeline step should use the right model for the job - not one model for everything.

### Phase 1 - Now (free OpenRouter + OpenCode Go)

| Step | Model | Reason |
|---|---|---|
| Scout (pick category/products) | DeepSeek V4 Flash (free) | Fast, 1M context, cheap |
| Generate | gpt-oss-120b (free) | OpenAI quality, strong on European languages |
| Generate (alt) | Gemma 4 31B (free) | If Danish quality is priority (140+ langs) |
| Review 1 (SEO/compliance) | Gemma 4 31B (free) | Thinking mode + multilingual |
| Review 2 (CRO/tone) | Arcee Trinity Thinking (free) | Reasoning model |
| Revise | gpt-oss-120b (free) | Same as generator |
| Validate | Code only | Zero LLM cost, deterministic |

### Phase 2 - After June 15 (Claude SDK credits)

| Step | Model | Reason |
|---|---|---|
| Scout | DeepSeek V4 Flash (free) | Still fast and free |
| Generate | Claude Sonnet | Best Danish prose, reliable JSON output |
| Review 1 | Gemma 4 31B (free) | Keep free, still excellent |
| Review 2 | Claude Haiku | Cheap, structured critique |
| Revise | Claude Sonnet | |

### Phase 3 - Upgrade (when revenue justifies)

| Step | Model | Reason |
|---|---|---|
| Generate | Claude Opus | Highest quality, ~$3-5/run |
| Everything else | Same as Phase 2 | Reviewers don't need Opus |

---

## Estimated Success Rates

| Stack | Success rate |
|---|---|
| Free OpenRouter (120B models) | 60-70% |
| Free + OpenCode Go (DeepSeek V4 Pro for gen) | 70-80% |
| Free + Claude Sonnet for generate | 85-90% |
| Free + Claude Opus for generate | 90-95% |

> Architecture work (hard gates, section anchors, deterministic orchestrator) adds ~10pp
> to each tier regardless of model. Do that first - model swap is a one-line config change.

---

## Key Design Decisions

- **Deterministic orchestrator in code** - pipeline logic lives in TypeScript, not in an agent prompt
- **LLMs as narrow workers** - each step is one focused SDK call, not a sub-agent spawn
- **Section-anchored placement** - never paragraph indices; agent specifies H2 section name
- **Hard publish gate** - server re-validates before posting, structured errors for retry
- **Publish to draft first** - trust period of 2-4 weeks before flipping to auto-publish
- **Cost cap per run** - hard token/dollar ceiling to prevent runaway loops
- **Max 3 publish attempts, 2 revision loops** per run

---

## Danish Language Note

Free OpenRouter models are stronger on Danish than initially assumed:
- Gemma 4 31B explicitly supports 140+ languages
- gpt-oss-120b (OpenAI training) covers European languages well
- Owl Alpha is agentic-first and works with OpenClaw runtime

Test Danish output quality early - run 5 generations and read critically before trusting
autonomous publishing.
