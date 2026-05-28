"""
Tests for the FastAPI tool server.
Uses TestClient - no running server needed.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from tool_server import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_fetch_products_endpoint():
    mock_product = MagicMock()
    mock_product.id = "1"
    mock_product.name = "Roomba j9+"
    mock_product.price_min = 3999.0
    mock_product.price_max = 4999.0
    mock_product.price_display = "Fra 3999 kr"
    mock_product.url = "https://www.pricerunner.dk/pl/1"
    mock_product.affiliate_url = "https://www.pricerunner.dk/pl/1?ref-site=test"
    mock_product.image_url = "https://cdn.pricerunner.dk/img/1.jpg"
    mock_product.rating = 4.5
    mock_product.review_count = 100
    mock_product.merchant_count = 8
    mock_product.category_id = 1613
    mock_product.category_name = "Robotstovsuger"

    mock_client = MagicMock()
    mock_client.fetch_products_by_category.return_value = [mock_product]

    with patch("testflow.orchestration.tools.PriceRunnerClient", return_value=mock_client):
        r = client.post("/tools/fetch_products", json={"category_id": 1613, "limit": 5})

    assert r.status_code == 200
    assert "products" in r.json()


def test_inject_compliance_endpoint():
    html = "<article><p>Test <a href='https://www.pricerunner.dk/pl/1'>link</a></p></article>"
    r = client.post("/tools/inject_compliance",
                    json={"html": html, "affiliate_id": "TEST", "partner_id": "PART"})
    assert r.status_code == 200
    body = r.json()
    assert "html" in body
    assert "transforms_applied" in body


def test_deterministic_audit_endpoint_passes():
    html = """<article>
      <div class="affiliate-disclosure">Affiliate</div>
      <a href="https://www.pricerunner.dk/pl/1?ref-site=X" rel="sponsored nofollow">link</a>
    </article>"""
    r = client.post("/tools/deterministic_audit", json={"html": html})
    assert r.status_code == 200
    assert r.json()["passed"] is True


def test_deterministic_audit_endpoint_fails_without_disclosure():
    html = "<article><p>No disclosure here.</p></article>"
    r = client.post("/tools/deterministic_audit", json={"html": html})
    assert r.status_code == 200
    assert r.json()["passed"] is False
    assert len(r.json()["errors"]) > 0


def test_discover_categories_endpoint():
    mock_cats = [{"name": "Robotstovsuger", "id": 1613, "parent": "Rengoring", "raw_id": "cl1613"}]
    with patch("tool_server.get_pricerunner_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.discover_categories.return_value = mock_cats
        mock_factory.return_value = mock_client
        r = client.post("/tools/discover_categories", json={"query": "robotstovsuger"})
    assert r.status_code == 200
    assert len(r.json()["categories"]) >= 1


def test_published_titles_endpoint():
    with patch("testflow.orchestration.tools.get_published_titles", return_value=["Title A", "Title B"]):
        r = client.get("/tools/published_titles", params={"site_name": "site_one"})
    assert r.status_code == 200
    assert "titles" in r.json()
