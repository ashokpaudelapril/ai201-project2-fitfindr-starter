"""
tests/test_tools.py

Unit tests for the three FitFindr tools, run with: pytest tests/

The search_listings tests hit the real dataset (no network). The LLM-backed
tools (suggest_outfit, create_fit_card) are tested for their guard/fallback
behavior so they pass WITHOUT a GROQ_API_KEY or network — the fallbacks are
themselves part of the spec'd error handling.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible query → empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter_substring():
    # "M" should match composite sizes like "S/M" and "M/L".
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    results = search_listings("vintage denim jeans", size=None, max_price=None)
    if len(results) >= 2:
        # First result should be at least as relevant as the last.
        def overlap(item):
            text = " ".join(
                [item["title"], item["description"], item["category"]]
                + item["style_tags"]
            ).lower()
            return sum(w in text for w in {"vintage", "denim", "jeans"})
        assert overlap(results[0]) >= overlap(results[-1])


# ── suggest_outfit ──────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_nonempty_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_with_wardrobe_returns_nonempty_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
    # Should be the guard message, not a crash or blank.
    assert "without an outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("   \n  ", item)
    assert "without an outfit" in result.lower()


def test_create_fit_card_valid_outfit_returns_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("Pair it with baggy jeans and chunky sneakers.", item)
    assert isinstance(result, str)
    assert result.strip() != ""
