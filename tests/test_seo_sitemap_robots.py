import xml.etree.ElementTree as ET

import pytest

from app.core.config import settings
from app.services.seo.crawl_policy import list_disallow_prefixes, list_indexable_paths
from app.services.seo.robots import build_robots_txt
from app.services.seo.site_url import get_site_url
from app.services.seo.sitemap_builder import build_sitemap_xml


@pytest.fixture(autouse=True)
def dev_site_url(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "site_url", "https://example.com")


def test_sitemap_xml_well_formed():
    xml = build_sitemap_xml()
    root = ET.fromstring(xml)
    assert root.tag.endswith("urlset")
    locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
    origin = get_site_url()
    assert locs
    for loc in locs:
        assert loc.startswith(origin)


def test_sitemap_excludes_forbidden():
    xml = build_sitemap_xml()
    root = ET.fromstring(xml)
    locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
    for loc in locs:
        path = loc.replace(get_site_url(), "")
        assert not path.startswith("/portal")
        assert not path.startswith("/admin")
        assert not path.startswith("/auth")
        assert "/v1/" not in path


def test_robots_disallow_and_sitemap_line():
    robots = build_robots_txt()
    assert "Disallow: /portal" in robots
    assert f"Sitemap: {get_site_url()}/sitemap.xml" in robots


def test_crwl_06_robots_disallow_does_not_block_indexable_paths():
    indexable = list_indexable_paths()
    disallow_prefixes = list_disallow_prefixes()
    for path in indexable:
        for prefix in disallow_prefixes:
            if prefix.endswith("/"):
                blocked = path.startswith(prefix)
            else:
                blocked = path == prefix.rstrip("/") or path.startswith(f"{prefix}/")
            assert not blocked, f"{path} blocked by {prefix}"
