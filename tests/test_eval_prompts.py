"""
Unit tests for the pure aggregation logic in scripts/eval_prompts.py.

The harness's write/judge paths hit live models, but the math that turns per-brief
records into the report (means, pass-rate, cost totals, failed-check tally) is pure
and worth pinning so a refactor can't silently skew an eval.

Run: python -m pytest tests/test_eval_prompts.py
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "eval_prompts.py"
_spec = importlib.util.spec_from_file_location("eval_prompts", _PATH)
ev = importlib.util.module_from_spec(_spec)
# Loading executes module-level imports (adapters, services.qa, services.similarity);
# those resolve via the sys.path inserts at the top of eval_prompts.py.
_spec.loader.exec_module(ev)


def _rec(draft_ok=True, qa_passed=True, fails=None, overall=80, seo=80, cro=80, read=80,
         words=900, uniq=0.1, wcost=0.05, jcost=0.01):
    return {
        "draft_ok": draft_ok,
        "qa_passed": qa_passed,
        "qa_failed_checks": fails or [],
        "scores": None if overall is None else {"overall": overall, "seo": seo, "cro": cro, "readability": read},
        "words": words,
        "uniqueness": uniq,
        "writer_cost": wcost,
        "judge_cost": jcost,
    }


def test_mean_ignores_none_and_rounds():
    assert ev._mean([80, 90, None]) == 85.0
    assert ev._mean([]) is None
    assert ev._mean([None]) is None


def test_aggregate_pass_rate_and_costs():
    recs = [_rec(qa_passed=True), _rec(qa_passed=False, fails=["QA-003"])]
    a = ev._aggregate(recs)
    assert a["n"] == 2
    assert a["draft_ok"] == 2
    assert a["qa_pass_rate"] == 0.5
    assert a["total_cost"] == 0.12  # (0.05+0.01) * 2
    assert a["failed_checks"] == {"QA-003": 1}


def test_aggregate_excludes_errored_drafts_from_score_means():
    # a draft that failed to generate should not drag the mean to 0 - it's excluded
    recs = [_rec(overall=90), _rec(draft_ok=False, overall=None, qa_passed=False)]
    a = ev._aggregate(recs)
    assert a["mean_overall"] == 90.0
    assert a["draft_ok"] == 1
    # pass-rate is computed over generated drafts only
    assert a["qa_pass_rate"] == 1.0


def test_aggregate_pass_rate_none_when_no_drafts():
    a = ev._aggregate([_rec(draft_ok=False, overall=None)])
    assert a["qa_pass_rate"] is None
    assert a["mean_overall"] is None


def test_generate_prompt_composes_base_plus_type():
    p = ev._generate_prompt("hero")
    # base persona + hero-specific module both present
    assert "affiliate" in p.lower()
    assert len(p) > len(ev._GEN_BASE.read_text(encoding="utf-8"))
