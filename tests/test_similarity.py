"""
Unit tests for api/services/similarity.py - shingle Jaccard near-dup detection.
Pure module, loaded by file path (no env/DB). Run: python -m pytest tests/test_similarity.py
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "services" / "similarity.py"
_spec = importlib.util.spec_from_file_location("similarity", _PATH)
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)


def test_identical_text_is_1():
    t = "den her robotstøvsuger er rigtig god til prisen og virker hver gang i hjemmet"
    assert sim.similarity(t, t) == 1.0


def test_disjoint_text_is_0():
    a = "robotstøvsuger med stærk sugeevne og lang batteritid til store hjem"
    b = "kaffemaskine med integreret kværn og mælkeskummer til den kræsne barista hjemme"
    assert sim.similarity(a, b) == 0.0


def test_markdown_links_unwrapped():
    a = "vi anbefaler [Dreame X50](https://x.dk?refsite=abc) som det bedste valg her"
    b = "vi anbefaler Dreame X50 som det bedste valg her"
    assert sim.similarity(a, b) > 0.9


def test_near_duplicate_scores_high():
    # same template, one product name swapped
    base = ("den er en stærk robotstøvsuger med god sugeevne og lang batteritid. "
            "vi synes den er pengene værd hvis du har et stort hjem med tæpper. {x} leverer.")
    a = base.format(x="dreame x50")
    b = base.format(x="roborock qrevo")
    assert sim.similarity(a, b) >= 0.7


def test_max_similarity_picks_best_and_index():
    text = "stærk sugeevne og lang batteritid gør den til et godt valg til store hjem"
    corpus = [
        "en helt anden tekst om havemøbler i teaktræ til terrassen om sommeren",
        "stærk sugeevne og lang batteritid gør den til et godt valg til store hjem",  # identical
    ]
    score, idx = sim.max_similarity(text, corpus)
    assert idx == 1 and score == 1.0


def test_empty_corpus():
    assert sim.max_similarity("noget tekst her til test", []) == (0.0, -1)
