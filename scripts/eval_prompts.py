"""
eval_prompts.py - Offline prompt eval / regression harness.

WHAT THIS IS (and is NOT)
  This is the *prompt eval*: it runs the writer over a FROZEN set of briefs
  (evals/briefs/, built by freeze_eval_briefs.py) and grades the output, so a
  prompt / model / system-prompt change can be measured on identical inputs.
  It is NOT part of content generation - it never publishes, and it runs the
  graders ONCE (no QA retry loop) so it measures the raw prompt, not the gate's
  ability to rescue a bad draft.

  The *article eval* (the QA gate + score_article step inside the pipeline) answers
  "is THIS article good enough to ship?". This harness answers "did my change make
  the SYSTEM better or worse?". It reuses the exact same graders so you tune against
  the bar production enforces.

GRADERS (both reused from the pipeline)
  - Deterministic: api/services/qa.py  (em-dash, forbidden phrases, word count,
    cross-article uniqueness within the run). Pass/fail per blocker.
  - LLM judge: prompts/score_v1.txt run by a SEPARATE adapter (default a different
    model than the writer, to avoid a model grading its own prose). Scores
    SEO / CRO / Readability / Overall.

USAGE (repo root)
  # cheap deterministic-only smoke (no judge cost):
  .venv/Scripts/python.exe scripts/eval_prompts.py --writer claude:claude-haiku-4-5-20251001 --no-judge --limit 1

  # full run, sonnet writer judged by opus, save the run:
  .venv/Scripts/python.exe scripts/eval_prompts.py --writer claude:claude-sonnet-4-6 --judge claude:claude-opus-4-8 --out evals/runs/sonnet-systemprompt.json

  # compare a new run against a saved baseline:
  .venv/Scripts/python.exe scripts/eval_prompts.py --writer claude:claude-sonnet-4-6 --baseline evals/runs/sonnet-systemprompt.json
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "api"))

from adapters import get_adapter  # noqa: E402
from services.qa import qa_service  # noqa: E402
from services.similarity import max_similarity  # noqa: E402

_BRIEFS_DIR = _ROOT / "evals" / "briefs"
_PROMPTS = _ROOT / "prompts"
_GEN_BASE = _PROMPTS / "generate_base.txt"
_SCORE_PROMPT = _PROMPTS / "score_v1.txt"

# article_type -> per-type generate module (mirrors load_prompts.GENERATE_TYPES)
_TYPE_FILES = {
    "single-product-review": "single-product-review.txt",
    "comparison": "comparison.txt",
    "hero": "hero.txt",
}


# ─── adapter spec ────────────────────────────────────────────────────────────

def _adapter(spec: str):
    name, _, model = spec.partition(":")
    return get_adapter(name, model=model or None)


def _model_of(spec: str) -> str:
    return spec.partition(":")[2] or spec


# ─── prompt assembly (mirrors load_prompts._assemble_generate_prompt) ─────────

def _generate_prompt(article_type: str) -> str:
    type_file = _TYPE_FILES.get(article_type)
    base = _GEN_BASE.read_text(encoding="utf-8")
    if type_file and (_PROMPTS / "types" / type_file).exists():
        module = (_PROMPTS / "types" / type_file).read_text(encoding="utf-8")
        return base + "\n\n" + module
    return base


# ─── brief loading ───────────────────────────────────────────────────────────

def _load_briefs(types: list[str] | None, limit: int | None) -> list[dict]:
    items: list[dict] = []
    for sub in sorted(p for p in _BRIEFS_DIR.iterdir() if p.is_dir()):
        if types and sub.name not in types:
            continue
        files = sorted(sub.glob("*.json"))
        if limit:
            files = files[:limit]
        for f in files:
            ctx = json.loads(f.read_text(encoding="utf-8"))
            items.append({"type": sub.name, "slug": f.stem, "context": ctx})
    return items


# ─── one brief: write, then grade ────────────────────────────────────────────

def _parse_draft(raw: str) -> dict | None:
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _write_draft(writer, ctx: dict) -> tuple[dict | None, float, str | None]:
    """Run the writer. Returns (draft_dict, cost, error)."""
    article_type = ctx.get("article_type", "single-product-review")
    gen_prompt = _generate_prompt(article_type)
    content = {
        "prompt": gen_prompt,
        "context": ctx,
        "previous_output": None,
        "step_name": "write_draft",
        "attempt": 1,
    }
    try:
        raw = writer.run(gen_prompt, content)
    except RuntimeError as e:
        return None, float(getattr(writer, "last_usage", {}).get("cost_usd", 0.0)), str(e)
    cost = float(getattr(writer, "last_usage", {}).get("cost_usd", 0.0))
    draft = _parse_draft(raw)
    if draft is None:
        return None, cost, "writer output was not parseable JSON"
    return draft, cost, None


def _judge(judge, ctx: dict, draft: dict) -> tuple[dict | None, float]:
    """Run the LLM judge (score_v1 prompt). Returns (scores, cost)."""
    score_prompt = _SCORE_PROMPT.read_text(encoding="utf-8")
    content = {
        "prompt": score_prompt,
        "context": ctx,
        "previous_output": json.dumps(draft, ensure_ascii=False),
        "step_name": "score_article",
        "attempt": 1,
    }
    try:
        raw = judge.run(score_prompt, content)
    except RuntimeError:
        return None, float(getattr(judge, "last_usage", {}).get("cost_usd", 0.0))
    cost = float(getattr(judge, "last_usage", {}).get("cost_usd", 0.0))
    scores = _parse_draft(raw)
    if not scores or "overall" not in scores:
        return None, cost
    return {k: scores.get(k) for k in ("seo", "cro", "readability", "overall")}, cost


def _grade_qa(ctx: dict, draft: dict, uniqueness: float | None) -> dict:
    """Deterministic QA on the draft, mirroring pipeline._run_python_qa inputs."""
    article = draft.get("article", "")
    seo = draft.get("seo", {}) or {}
    qa_ctx = {
        **ctx,
        "meta_description": seo.get("description", ""),
        "min_words": ctx.get("brief", {}).get("writing_rules", {}).get("min_words", 700),
    }
    if uniqueness is not None:
        qa_ctx["uniqueness_score"] = uniqueness
    return qa_service.run(article, qa_ctx)


# ─── aggregation ─────────────────────────────────────────────────────────────

def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _aggregate(records: list[dict]) -> dict:
    n = len(records)
    graded = [r for r in records if r["draft_ok"]]
    failed = Counter()
    for r in records:
        for c in r["qa_failed_checks"]:
            failed[c] += 1
    return {
        "n": n,
        "draft_ok": sum(1 for r in records if r["draft_ok"]),
        "qa_pass_rate": round(sum(1 for r in graded if r["qa_passed"]) / len(graded), 2) if graded else None,
        "failed_checks": dict(failed.most_common()),
        "mean_overall": _mean([r["scores"]["overall"] for r in graded if r["scores"]]),
        "mean_seo": _mean([r["scores"]["seo"] for r in graded if r["scores"]]),
        "mean_cro": _mean([r["scores"]["cro"] for r in graded if r["scores"]]),
        "mean_readability": _mean([r["scores"]["readability"] for r in graded if r["scores"]]),
        "mean_words": _mean([r["words"] for r in graded]),
        "mean_uniqueness": _mean([r["uniqueness"] for r in graded if r["uniqueness"] is not None]),
        "writer_cost": round(sum(r["writer_cost"] for r in records), 4),
        "judge_cost": round(sum(r["judge_cost"] for r in records), 4),
        "total_cost": round(sum(r["writer_cost"] + r["judge_cost"] for r in records), 4),
    }


# ─── reporting ───────────────────────────────────────────────────────────────

def _fmt(v, suffix="") -> str:
    return "-" if v is None else f"{v}{suffix}"


def _print_report(run: dict, baseline: dict | None) -> None:
    print("\n" + "=" * 72)
    print(f"PROMPT EVAL  writer={run['meta']['writer']}  judge={run['meta']['judge']}")
    print("=" * 72)

    by_type = run["aggregates"]["by_type"]
    cols = ["type", "n", "qa_pass", "overall", "seo", "cro", "read", "words", "uniq", "cost$"]
    print(f"{cols[0]:<22}{cols[1]:>4}{cols[2]:>9}{cols[3]:>9}{cols[4]:>6}{cols[5]:>6}{cols[6]:>6}{cols[7]:>7}{cols[8]:>7}{cols[9]:>9}")
    for t, a in {**by_type, "OVERALL": run["aggregates"]["overall"]}.items():
        pass_rate = _fmt(None if a["qa_pass_rate"] is None else f"{int(a['qa_pass_rate']*100)}%")
        uniq = _fmt(None if a["mean_uniqueness"] is None else f"{int(a['mean_uniqueness']*100)}%")
        print(
            f"{t:<22}{a['n']:>4}{pass_rate:>9}{_fmt(a['mean_overall']):>9}"
            f"{_fmt(a['mean_seo']):>6}{_fmt(a['mean_cro']):>6}{_fmt(a['mean_readability']):>6}"
            f"{_fmt(a['mean_words']):>7}{uniq:>7}{a['total_cost']:>9.4f}"
        )

    overall = run["aggregates"]["overall"]
    if overall["failed_checks"]:
        print("\nTop failing QA checks:")
        for cid, cnt in overall["failed_checks"].items():
            print(f"  {cid}: {cnt}")

    # per-brief detail
    print("\nPer-brief:")
    for r in run["briefs"]:
        sc = r["scores"]["overall"] if r["scores"] else "-"
        status = "PASS" if r["qa_passed"] else ("ERR" if not r["draft_ok"] else "FAIL")
        extra = "" if r["draft_ok"] else f"  ({r['error']})"
        fails = "" if r["qa_passed"] or not r["draft_ok"] else f"  [{','.join(r['qa_failed_checks'])}]"
        print(f"  {status:<4} {r['type']:<12} {r['slug'][:34]:<34} overall={sc} words={r['words']}{fails}{extra}")

    if baseline:
        b = baseline["aggregates"]["overall"]
        o = overall
        print("\n" + "-" * 72)
        print(f"vs BASELINE ({baseline['meta']['writer']}, {baseline['meta'].get('timestamp','?')[:19]})")

        def delta(new, old, suffix="", pct=False):
            if new is None or old is None:
                return "-"
            d = (new - old)
            if pct:
                return f"{new*100:.0f}% ({'+' if d>=0 else ''}{d*100:.0f}pp)"
            return f"{new} ({'+' if d>=0 else ''}{round(d,1)})"
        print(f"  overall:   {delta(o['mean_overall'], b['mean_overall'])}")
        print(f"  qa_pass:   {delta(o['qa_pass_rate'], b['qa_pass_rate'], pct=True)}")
        print(f"  uniqueness:{delta(o['mean_uniqueness'], b['mean_uniqueness'], pct=True)}")
        print(f"  total_cost: ${o['total_cost']} (baseline ${b['total_cost']})")
    print()


# ─── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Offline prompt eval / regression harness")
    ap.add_argument("--writer", default="claude",
                    help="Adapter[:model] under test (the prompt/model you are tuning). Default: claude")
    ap.add_argument("--judge", default="claude:claude-haiku-4-5-20251001",
                    help="Adapter[:model] for the LLM judge. Keep it DIFFERENT from --writer to avoid "
                         "self-preference; a stronger model (e.g. claude:claude-opus-4-8) gives more "
                         "reliable scores. Default: claude:claude-haiku-4-5-20251001")
    ap.add_argument("--no-judge", action="store_true", help="Skip the LLM judge (deterministic QA only, no judge cost)")
    ap.add_argument("--types", default=None, help="Comma-separated subset of brief types (review,comparison,hero)")
    ap.add_argument("--limit", type=int, default=None, help="Max briefs per type (for cheap smoke runs)")
    ap.add_argument("--out", default=None, help="Write the run JSON here (e.g. evals/runs/<name>.json)")
    ap.add_argument("--baseline", default=None, help="Compare against a saved run JSON")
    args = ap.parse_args()

    types = [t.strip() for t in args.types.split(",")] if args.types else None
    briefs = _load_briefs(types, args.limit)
    if not briefs:
        print(f"No briefs found under {_BRIEFS_DIR}. Run freeze_eval_briefs.py first.")
        sys.exit(1)

    writer = _adapter(args.writer)
    judge = None if args.no_judge else _adapter(args.judge)
    if judge and _model_of(args.judge) == _model_of(args.writer):
        print("WARNING: judge and writer use the same model - scores carry self-preference bias.\n")

    print(f"Running {len(briefs)} brief(s): writer={args.writer} judge={'(none)' if args.no_judge else args.judge}")

    # Pass 1: write + judge every brief
    for b in briefs:
        draft, wcost, err = _write_draft(writer, b["context"])
        b.update(draft_ok=draft is not None, draft=draft, writer_cost=wcost, error=err,
                 judge_cost=0.0, scores=None)
        if draft is None:
            print(f"  [{b['type']}] {b['slug']}: ERROR - {err}")
            continue
        b["words"] = len(draft.get("article", "").split())
        if judge:
            scores, jcost = _judge(judge, b["context"], draft)
            b["scores"], b["judge_cost"] = scores, jcost
        ov = b["scores"]["overall"] if b["scores"] else "-"
        print(f"  [{b['type']}] {b['slug']}: words={b['words']} overall={ov} (${wcost + b['judge_cost']:.4f})")

    # Pass 2: cross-article uniqueness within each type, then deterministic QA
    for b in briefs:
        if not b["draft_ok"]:
            b.update(words=0, uniqueness=None, qa_passed=False, qa_failed_checks=[])
            continue
        corpus = [o["draft"].get("article", "") for o in briefs
                  if o is not b and o["draft_ok"] and o["type"] == b["type"]]
        uniq = max_similarity(b["draft"].get("article", ""), corpus)[0] if corpus else None
        b["uniqueness"] = uniq
        qa = _grade_qa(b["context"], b["draft"], uniq)
        b["qa_passed"] = qa["passed"]
        b["qa_failed_checks"] = [r["check_id"] for r in qa["results"] if not r["passed"] and r["severity"] == "BLOCKER"]

    # records for serialisation (drop the bulky draft body)
    records = [{k: v for k, v in b.items() if k != "draft"} for b in briefs]
    by_type: dict[str, dict] = {}
    for t in sorted({r["type"] for r in records}):
        by_type[t] = _aggregate([r for r in records if r["type"] == t])

    run = {
        "meta": {
            "writer": args.writer,
            "judge": "(none)" if args.no_judge else args.judge,
            "timestamp": datetime.now().isoformat(),
        },
        "aggregates": {"by_type": by_type, "overall": _aggregate(records)},
        "briefs": records,
    }

    baseline = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    _print_report(run, baseline)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Run written to {out}")


if __name__ == "__main__":
    main()
