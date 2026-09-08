import pytest

from app.core.config import settings
from app.services.seo.crawl_policy import (
    STATIC_MARKETING_PATHS,
    list_indexable_paths,
    load_documentation_paths,
    paths_blocked_by_robots,
)


@pytest.fixture(autouse=True)
def dev_site_url(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "https://example.com")


def test_static_allowlist_matches_frontend_public_routes():
    paths = list_indexable_paths()
    for path in STATIC_MARKETING_PATHS:
        assert path in paths
    assert "/request-trial" in paths


def test_doc_manifest_merged():
    doc_paths = load_documentation_paths()
    assert len(doc_paths) >= 20
    assert "/documentation/getting-started/overview" in doc_paths
    assert "/documentation" in list_indexable_paths()


def test_indexable_paths_exclude_clinical_and_app():
    paths = list_indexable_paths()
    for path in paths:
        assert not path.startswith("/portal")
        assert not path.startswith("/admin")
        assert not path.startswith("/auth")
        assert not path.startswith("/doctor-support")
        assert "/v1/" not in path
        assert "/encounter" not in path
        assert "/customer" not in path


def test_crwl_06_no_indexable_path_blocked_by_robots():
    paths = list_indexable_paths()
    assert paths_blocked_by_robots(paths) == []
