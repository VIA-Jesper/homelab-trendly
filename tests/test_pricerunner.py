"""
Tests for PriceRunnerClient.
All HTTP calls mocked - no real PriceRunner requests.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from testflow.content.pricerunner import PriceRunnerClient, filter_by_explicit
from testflow.models import PRProduct

MOCK_PRODUCT_RESPONSE = {
    "products": [
        {
            "id": "1234567",
            "name": "iRobot Roomba j9+",
            "price": {"min": 4199, "max": 5499},
            "url": "/pl/1234567/iRobot-Roomba-j9-plus",
            "image": {"url": "https://cdn.pricerunner.com/images/roomba.jpg"},
            "rating": {"score": 4.7, "count": 312},
            "merchantCount": 8,
            "category": {"id": 1613, "name": "Robotstovsuger"},
        }
    ]
}

MOCK_CATEGORY_TREE = {
    "children": [
        {
            "id": "cl1613",
            "name": "Robotstovsuger",
            "children": [],
        },
        {
            "id": "cl67",
            "name": "Stovsugere",
            "children": [],
        },
    ]
}


@pytest.fixture
def client(tmp_path):
    return PriceRunnerClient(cache_dir=tmp_path)


def test_fetch_products_returns_prproduct_list(client):
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE):
        products = client.fetch_products_by_category(1613, limit=5)
    assert len(products) == 1
    assert isinstance(products[0], PRProduct)
    assert products[0].name == "iRobot Roomba j9+"


def test_affiliate_url_appends_ref_param(client):
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE):
        with patch.dict("os.environ", {"PRICERUNNER_AFFILIATE_ID": "my-ref-id"}):
            products = client.fetch_products_by_category(1613)
            # affiliate_url reads os.environ at access time - must check inside the patch context
            assert "ref-site=my-ref-id" in products[0].affiliate_url


def test_cache_is_used_on_second_call(client, tmp_path):
    """Second call for same category should read from cache, not make HTTP request."""
    with patch.object(client, "_get", return_value=MOCK_PRODUCT_RESPONSE) as mock_get:
        client.fetch_products_by_category(1613)
        client.fetch_products_by_category(1613)
    assert mock_get.call_count == 1


def test_discover_categories_returns_matches(client):
    with patch.object(client, "_get", return_value=MOCK_CATEGORY_TREE):
        results = client.discover_categories("stovsug")
    assert len(results) >= 1
    assert any(r["id"] == 1613 for r in results)


def test_filter_by_explicit_matches_case_insensitive():
    products = [
        PRProduct(id="1", name="iRobot Roomba j9+", price_min=4199, price_max=5499,
                  url="https://pricerunner.dk/pl/1", image_url="", merchant_count=5,
                  category_id=1613, category_name="test"),
        PRProduct(id="2", name="Ecovacs Deebot X2", price_min=3999, price_max=4999,
                  url="https://pricerunner.dk/pl/2", image_url="", merchant_count=3,
                  category_id=1613, category_name="test"),
    ]
    result = filter_by_explicit(products, ["roomba"])
    assert len(result) == 1
    assert result[0].name == "iRobot Roomba j9+"


def test_filter_by_explicit_empty_returns_all():
    products = [
        PRProduct(id="1", name="Product A", price_min=100, price_max=200,
                  url="https://pricerunner.dk/pl/1", image_url="", merchant_count=1,
                  category_id=1, category_name="cat"),
    ]
    result = filter_by_explicit(products, [])
    assert result == products


def test_product_price_display():
    p = PRProduct(id="1", name="Test", price_min=1234.5, price_max=1500,
                  url="https://pricerunner.dk/pl/1", image_url="", merchant_count=2,
                  category_id=1, category_name="test")
    # Python's :.0f uses banker's rounding: 1234.5 rounds to 1234 (even)
    assert "1234" in p.price_display
    assert "kr" in p.price_display
