"""
Unit tests for api/services/internal_links.py - the related-articles cluster builder.
Pure module, loaded by file path. Run: python -m pytest tests/test_internal_links.py
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "services" / "internal_links.py"
_spec = importlib.util.spec_from_file_location("internal_links", _PATH)
il = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(il)


def test_empty_candidates_returns_empty():
    assert il.build_related_section([], "husforbegyndere.dk") == ""


def test_uses_title_when_present():
    out = il.build_related_section(
        [{"slug": "dreame-x50-test", "title": "Dreame X50 test"}], "husforbegyndere.dk")
    assert "## Læs også" in out
    assert "[Dreame X50 test](https://husforbegyndere.dk/dreame-x50-test/)" in out


def test_falls_back_to_deslugified_slug():
    out = il.build_related_section([{"slug": "bedste-robotstoevsugere-guide", "title": None}], "x.dk")
    assert "[Bedste robotstoevsugere guide](https://x.dk/bedste-robotstoevsugere-guide/)" in out


def test_respects_max_links():
    cands = [{"slug": f"a-{i}", "title": None} for i in range(10)]
    out = il.build_related_section(cands, "x.dk", max_links=3)
    assert out.count("- [") == 3


def test_dedupes_slugs():
    cands = [{"slug": "same", "title": "A"}, {"slug": "same", "title": "B"}]
    out = il.build_related_section(cands, "x.dk")
    assert out.count("- [") == 1


def test_skips_blank_slugs():
    out = il.build_related_section([{"slug": "", "title": "x"}, {"slug": "  ", "title": "y"}], "x.dk")
    assert out == ""


def test_deslugify():
    assert il.deslugify("bedste-robotstoevsugere") == "Bedste robotstoevsugere"
    assert il.deslugify("") == ""
