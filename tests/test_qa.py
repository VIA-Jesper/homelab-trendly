"""
Unit tests for the new QA gate checks (api/services/qa.py): QA-004 no em/en
dashes, QA-005 forbidden AI-slop phrases + brief forbidden superlatives.

qa.py is loaded by file path with api/ on sys.path so its
`from interfaces.qa_check import IQACheck` resolves, without dragging in the
services package __init__ (which needs config/DB).
Run: python -m pytest tests/test_qa.py
"""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))  # for `from interfaces.qa_check import IQACheck`
_spec = importlib.util.spec_from_file_location("qa", ROOT / "api" / "services" / "qa.py")
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)

NoDashCheck = qa.NoDashCheck
ForbiddenPhraseCheck = qa.ForbiddenPhraseCheck
UniquenessCheck = qa.UniquenessCheck
QAService = qa.QAService


# ─── QA-004 dashes ───────────────────────────────────────────────────────────

def test_em_dash_blocks():
    assert NoDashCheck().evaluate("Den er hurtig — og god.", {})["passed"] is False

def test_en_dash_blocks():
    assert NoDashCheck().evaluate("pris 100–200 kr", {})["passed"] is False

def test_plain_hyphen_passes():
    r = NoDashCheck().evaluate("Den er hurtig - og god. 100-200 kr.", {})
    assert r["passed"] is True


# ─── QA-005 forbidden phrases ────────────────────────────────────────────────

def test_forbidden_phrase_blocks():
    r = ForbiddenPhraseCheck().evaluate("Det er værd at bemærke at den er god.", {})
    assert r["passed"] is False
    assert "bemærke" in r["message"].lower()

def test_brief_forbidden_superlative_blocks():
    ctx = {"brief": {"compliance": {"forbidden_superlatives": ["bedste på markedet"]}}}
    r = ForbiddenPhraseCheck().evaluate("Den er bedste på markedet.", ctx)
    assert r["passed"] is False

def test_clean_text_passes():
    r = ForbiddenPhraseCheck().evaluate("En god robotstøvsuger til prisen.", {})
    assert r["passed"] is True

def test_case_insensitive():
    assert ForbiddenPhraseCheck().evaluate("SOM NÆVNT OVENFOR er den god.", {})["passed"] is False

def test_opener_pattern_with_product_name_between():
    # the system-check gap: "i denne <product> anmeldelse" must be caught, not just the literal
    r = ForbiddenPhraseCheck().evaluate(
        "I denne Dreame X50 Ultra Black anmeldelse ser vi på flagskibet.", {})
    assert r["passed"] is False

def test_opener_pattern_variants():
    for txt in ("I denne test af robotten kigger vi nærmere.",
                "I dette indlæg gennemgår vi modellen.",
                "I denne grundige sammenligning af de seks ser vi på."):
        assert ForbiddenPhraseCheck().evaluate(txt, {})["passed"] is False, txt

def test_opener_pattern_no_false_positive():
    # "denne" and a review-ish noun far apart / unrelated should not trip
    assert ForbiddenPhraseCheck().evaluate(
        "Denne robot er god. Vi lavede en grundig test af sugeevnen senere i hjemmet.", {})["passed"] is True


# ─── QA-006 uniqueness (gates on injected score) ─────────────────────────────

def test_uniqueness_no_score_passes():
    assert UniquenessCheck().evaluate("text", {})["passed"] is True

def test_uniqueness_below_threshold_passes():
    r = UniquenessCheck().evaluate("text", {"uniqueness_score": 0.10})
    assert r["passed"] is True

def test_uniqueness_above_threshold_blocks():
    r = UniquenessCheck().evaluate("text", {"uniqueness_score": 0.80})
    assert r["passed"] is False
    assert "%" in r["message"]

def test_uniqueness_custom_threshold():
    ctx = {"uniqueness_score": 0.25, "uniqueness_threshold": 0.20}
    assert UniquenessCheck().evaluate("text", ctx)["passed"] is False


# ─── service integration ─────────────────────────────────────────────────────

def test_service_registers_new_checks():
    ids = {c.check_id for c in QAService()._checks}
    assert {"QA-001", "QA-002", "QA-003", "QA-004", "QA-005", "QA-006"} <= ids

def test_service_blocks_on_near_duplicate():
    res = QAService().run(
        "En solid robotstøvsuger til prisen. Den virker hver gang.",
        {"meta_description": "x" * 130, "min_words": 1, "uniqueness_score": 0.9},
    )
    assert res["passed"] is False

def test_service_blocks_on_em_dash():
    # meta 120-160 + low min_words isolates the dash failure from the other blockers
    res = QAService().run("God tekst — med em dash her.", {"meta_description": "x" * 130, "min_words": 1})
    assert res["passed"] is False
    assert res["blocker_failures"] >= 1

def test_service_passes_clean_article():
    res = QAService().run(
        "En solid robotstøvsuger til prisen. Den virker hver gang.",
        {"meta_description": "x" * 130, "min_words": 1},
    )
    assert res["passed"] is True
