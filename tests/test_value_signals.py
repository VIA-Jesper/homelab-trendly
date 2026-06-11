"""
Unit tests for api/services/value_signals.py - comparative facts for a product set.

Loaded by file path (like test_dedup) so the pure module is testable with no env /
no DB - the `services` package __init__ pulls in config/DB which we don't want here.
Run: python -m pytest tests/test_value_signals.py
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "services" / "value_signals.py"
_spec = importlib.util.spec_from_file_location("value_signals", _PATH)
value_signals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(value_signals)

compute = value_signals.compute_value_signals
_first_number = value_signals._first_number


# ─── number parsing ──────────────────────────────────────────────────────────

def test_first_number_plain_unit():
    assert _first_number("5200 mAh") == 5200.0

def test_first_number_decimal_comma():
    assert _first_number("0,3 l") == 0.3
    assert _first_number("4,5") == 4.5

def test_first_number_thousands_dot():
    assert _first_number("1.299") == 1299.0

def test_first_number_mixed_separators():
    assert _first_number("1.299,50 kr") == 1299.5

def test_first_number_none():
    assert _first_number("ja") is None
    assert _first_number("") is None


# ─── price comparison ────────────────────────────────────────────────────────

def _p(pid, price, **specs):
    return {"id": pid, "name": pid, "price_kr": price, "specs": specs}


def test_price_ranking_and_position():
    vs = compute([_p("a", 1000), _p("b", 3000), _p("c", 2000)])
    pp = vs["per_product"]
    assert pp["a"]["price_position"] == "cheapest"
    assert pp["a"]["price_rank"] == 1
    assert pp["a"]["price_vs_cheapest_kr"] == 0
    assert pp["b"]["price_position"] == "most_expensive"
    assert pp["b"]["price_vs_cheapest_kr"] == 2000
    assert pp["c"]["price_position"] == "mid"
    assert vs["price"] == {"min": 1000.0, "max": 3000.0, "median": 2000.0}


def test_single_product_has_price_only_no_comparison():
    vs = compute([_p("solo", 2499, kapacitet="5200 mAh")])
    assert vs["set_size"] == 1
    entry = vs["per_product"]["solo"]
    assert entry["price_kr"] == 2499.0
    # nothing to compare against -> no rank, no leads, no unique specs
    assert "price_rank" not in entry
    assert "spec_leads" not in entry
    assert "unique_specs" not in entry


# ─── spec leads ──────────────────────────────────────────────────────────────

def test_spec_lead_highest_and_lowest():
    vs = compute([
        _p("a", 1000, sugeevne="2000 pa", stoej="65 dB"),
        _p("b", 2000, sugeevne="8000 pa", stoej="55 dB"),
    ])
    pp = vs["per_product"]
    a_specs = {(l["spec"], l["position"]) for l in pp["a"].get("spec_leads", [])}
    b_specs = {(l["spec"], l["position"]) for l in pp["b"].get("spec_leads", [])}
    assert ("sugeevne", "lowest") in a_specs
    assert ("stoej", "highest") in a_specs
    assert ("sugeevne", "highest") in b_specs
    assert ("stoej", "lowest") in b_specs


def test_identical_specs_are_not_compared():
    # both have the same value -> not a differentiator, no spec_leads
    vs = compute([_p("a", 1000, vaegt="3 kg"), _p("b", 2000, vaegt="3 kg")])
    assert "spec_leads" not in vs["per_product"]["a"]
    assert "spec_leads" not in vs["per_product"]["b"]


def test_platform_specs_excluded_from_comparison():
    # rating / watchedLabel etc. must never become a "value" signal
    vs = compute([
        _p("a", 1000, rating="4.5", watchedLabel="500", sugeevne="2000 pa"),
        _p("b", 2000, rating="3.0", watchedLabel="100", sugeevne="8000 pa"),
    ])
    leads_a = {l["spec"] for l in vs["per_product"]["a"].get("spec_leads", [])}
    assert "rating" not in leads_a
    assert "watchedLabel" not in leads_a
    assert "sugeevne" in leads_a or "sugeevne" in {
        l["spec"] for l in vs["per_product"]["b"].get("spec_leads", [])
    }


def test_unique_specs_detected():
    vs = compute([
        _p("a", 1000, moppe="ja", sugeevne="2000 pa"),
        _p("b", 2000, sugeevne="8000 pa"),
    ])
    assert vs["per_product"]["a"].get("unique_specs") == ["moppe"]
    assert "unique_specs" not in vs["per_product"]["b"]


def test_empty_set():
    vs = compute([])
    assert vs["set_size"] == 0
    assert vs["per_product"] == {}
