import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@pytest.fixture
def prod_client(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "site_url", "https://example.com")
    return TestClient(create_app())


@pytest.fixture
def dev_client(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "https://example.com")
    return TestClient(create_app())


def test_openapi_disabled_in_production(prod_client):
    assert prod_client.get("/openapi.json").status_code == 404
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404


def test_openapi_available_in_development(dev_client):
    assert dev_client.get("/openapi.json").status_code == 200


def test_v1_responses_include_x_robots_noindex(dev_client):
    res = dev_client.get("/v1/seo/prerender-paths")
    assert res.status_code == 200
    assert res.headers.get("x-robots-tag") == "noindex"


def test_sitemap_not_indexed_via_x_robots(dev_client):
    res = dev_client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "x-robots-tag" not in res.headers
