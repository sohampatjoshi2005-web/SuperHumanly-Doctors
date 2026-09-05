import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@pytest.fixture(autouse=True)
def dev_site_url(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "https://example.com")


@pytest.fixture
def client():
    return TestClient(create_app())


def test_sitemap_xml_route(client):
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert "https://example.com/pricing" in res.text
    assert "/portal" not in res.text


def test_robots_txt_route(client):
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "Disallow: /portal" in res.text
    assert "Sitemap: https://example.com/sitemap.xml" in res.text


def test_prerender_paths_route(client):
    res = client.get("/v1/seo/prerender-paths")
    assert res.status_code == 200
    data = res.json()
    assert "/privacy" in data["paths"]
    assert "/terms" in data["paths"]
