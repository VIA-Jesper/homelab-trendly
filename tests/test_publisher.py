"""
Tests for the WordPress publisher client.
All HTTP calls mocked with pytest-httpx.
"""
import pytest
from pytest_httpx import HTTPXMock
from testflow.publisher.client import WordPressClient
from testflow.models import Article, YoastMeta

SITE_URL = "https://www.site-one.dk"


@pytest.fixture
def client():
    return WordPressClient(SITE_URL, "testflow-bot", "fake-app-password")


@pytest.fixture
def minimal_article():
    return Article(
        title="Test artikel",
        slug="test-artikel",
        excerpt="En test",
        body_html="<p>Indhold</p>",
        yoast_meta=YoastMeta(
            focus_keyword="test",
            meta_description="Test meta",
            seo_title="Test | Site One",
        ),
        categories=["Robotstovsuger"],
        tags=["test"],
    )


def test_create_post_sends_draft_status(httpx_mock: HTTPXMock, client, minimal_article):
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/categories?search=Robotstovsuger", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/categories", json={"id": 5})
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/tags?search=test", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/tags", json={"id": 10})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/posts",
                            json={"id": 42, "link": f"{SITE_URL}/?p=42"})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/yoast-bridge/v1/post/42/meta",
                            json={"updated": {"focus_keyword": "test"}})

    result = client.create_post(minimal_article)
    assert result.post_id == 42
    assert "42" in result.post_url

    # Verify it was sent as draft
    post_requests = [r for r in httpx_mock.get_requests() if "/wp/v2/posts" in str(r.url) and r.method == "POST"]
    assert len(post_requests) == 1
    import json
    body = json.loads(post_requests[0].content)
    assert body["status"] == "draft"


def test_create_post_uses_existing_category(httpx_mock: HTTPXMock, client, minimal_article):
    """Should not create a new category if one already exists."""
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/categories?search=Robotstovsuger",
                            json=[{"id": 5, "name": "Robotstovsuger"}])
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/tags?search=test", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/tags", json={"id": 10})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/posts",
                            json={"id": 43, "link": f"{SITE_URL}/?p=43"})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/yoast-bridge/v1/post/43/meta",
                            json={"updated": {}})

    result = client.create_post(minimal_article)
    assert result.post_id == 43

    # Only one categories request (the GET), no POST to categories
    cat_posts = [r for r in httpx_mock.get_requests() if "/categories" in str(r.url) and r.method == "POST"]
    assert len(cat_posts) == 0


def test_yoast_meta_is_set_after_post_creation(httpx_mock: HTTPXMock, client, minimal_article):
    """Yoast bridge must be called after post is created."""
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/categories?search=Robotstovsuger", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/categories", json={"id": 5})
    httpx_mock.add_response(url=f"{SITE_URL}/wp-json/wp/v2/tags?search=test", json=[])
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/tags", json={"id": 10})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/wp/v2/posts",
                            json={"id": 55, "link": f"{SITE_URL}/?p=55"})
    httpx_mock.add_response(method="POST", url=f"{SITE_URL}/wp-json/yoast-bridge/v1/post/55/meta",
                            json={"updated": {"focus_keyword": "test"}})

    result = client.create_post(minimal_article)
    yoast_requests = [r for r in httpx_mock.get_requests() if "yoast-bridge" in str(r.url)]
    assert len(yoast_requests) == 1
    import json
    yoast_body = json.loads(yoast_requests[0].content)
    assert yoast_body["focus_keyword"] == "test"
