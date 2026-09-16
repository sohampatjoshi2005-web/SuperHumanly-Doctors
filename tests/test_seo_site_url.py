import pytest

from app.core.config import settings
from app.services.seo import site_url as site_url_module
from app.services.seo.site_url import absolute_url, get_site_url, normalize_origin


@pytest.fixture(autouse=True)
def reset_site_url_cache():
    site_url_module._warned_dev_fallback = False
    yield
    site_url_module._warned_dev_fallback = False


def test_normalize_origin_strips_trailing_slash():
    assert normalize_origin("https://example.com/") == "https://example.com"


def test_get_site_url_development_fallback(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "")
    assert get_site_url() == "http://localhost:5173"


def test_get_site_url_uses_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "https://superhumanlymedical.io")
    assert get_site_url() == "https://superhumanlymedical.io"
    assert absolute_url("/pricing") == "https://superhumanlymedical.io/pricing"


def test_get_site_url_production_requires_https(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "site_url", "")
    with pytest.raises(ValueError, match="SITE_URL is required"):
        get_site_url()

    monkeypatch.setattr(settings, "site_url", "http://example.com")
    with pytest.raises(ValueError, match="https"):
        get_site_url()
