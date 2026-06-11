"""
Unit tests for api/services/dedup.py - the canonical product/slot keys.

dedup.py is a pure, stdlib-only module. We load it directly by file path rather
than `from services.dedup import ...` on purpose: the `services` package
__init__ eagerly imports pipeline_service -> config.Settings(), which requires
DATABASE_URL/API_KEY. The keys are pure and must be testable with no env / no DB,
so we bypass the package import entirely.
Run: python -m pytest tests/test_dedup.py
"""

import importlib.util
import pathlib

_DEDUP_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "services" / "dedup.py"
_spec = importlib.util.spec_from_file_location("dedup", _DEDUP_PATH)
dedup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dedup)

canonical_product_key = dedup.canonical_product_key
normalize_category = dedup.normalize_category
normalize_text = dedup.normalize_text
slot_key = dedup.slot_key


# ── normalize_text ───────────────────────────────────────────────────────────

def test_normalize_lowercases_and_collapses():
    assert normalize_text("  Roborock   S8  Pro ") == "roborock s8 pro"


def test_normalize_strips_punctuation_keeps_nordic():
    assert normalize_text("Bosch Serie-6, WAU28T64 (æøå)") == "bosch serie 6 wau28t64 æøå"


# ── canonical_product_key ────────────────────────────────────────────────────

def test_product_key_prefers_id_from_url():
    assert canonical_product_key("Whatever", url="https://www.pricerunner.dk/pl/19-3206825946/x") == "pr:3206825946"


def test_product_key_normalizes_pr_prefix_and_bare_id_match():
    # 'pr_3206825946' (brief format) and '3206825946' (regex format) must agree.
    assert canonical_product_key("X", pid="pr_3206825946") == "pr:3206825946"
    assert canonical_product_key("X", pid="3206825946") == "pr:3206825946"


def test_product_key_name_fallback_is_order_independent():
    # Harmless word reordering between snapshots must not read as a new product.
    a = canonical_product_key("Roborock S8 Pro Ultra")
    b = canonical_product_key("Ultra Pro S8 Roborock")
    assert a == b == "nm:pro roborock s8 ultra"


def test_product_key_name_variant_with_punctuation_matches():
    a = canonical_product_key("Bosch Serie 6 WAU28T64")
    b = canonical_product_key("Bosch WAU28T64 Serie 6")
    assert a == b


def test_url_id_wins_over_name():
    # Same product id, different displayed names -> same key.
    a = canonical_product_key("Roborock S8 Pro Ultra (hvid)", url="https://www.pricerunner.dk/pl/19-111/x")
    b = canonical_product_key("Roborock S8 Pro Ultra", url="https://www.pricerunner.dk/pl/19-111/y")
    assert a == b == "pr:111"


# ── slot_key ─────────────────────────────────────────────────────────────────

def test_slot_single():
    assert slot_key("single-product-review", "Robotstøvsugere", ["pr:1"]) == "robotstøvsugere:single:pr:1"


def test_slot_comparison_is_order_independent():
    a = slot_key("comparison", "robotstøvsugere", ["pr:2", "pr:1"])
    b = slot_key("comparison", "robotstøvsugere", ["pr:1", "pr:2"])
    assert a == b == "robotstøvsugere:comparison:pr:1|pr:2"


def test_slot_roundup_by_product_set_when_no_segment():
    a = slot_key("hero", "robotstøvsugere", ["pr:1", "pr:2"])
    b = slot_key("hero", "robotstøvsugere", ["pr:2", "pr:1"])
    assert a == b == "robotstøvsugere:roundup:pr:1|pr:2"


def test_slot_roundup_segment_distinct_despite_same_products():
    # The Phase 1 win: same products, different segment -> different slot.
    pets = slot_key("hero", "robotstøvsugere", ["pr:1", "pr:2"], segment="til kæledyr")
    small = slot_key("hero", "robotstøvsugere", ["pr:1", "pr:2"], segment="til små lejligheder")
    assert pets != small
    assert pets == "robotstøvsugere:roundup:til-kæledyr"


def test_normalize_category_drift():
    assert normalize_category("Robotstøvsugere") == normalize_category("  robotstøvsugere ")
