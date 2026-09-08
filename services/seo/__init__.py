"""SEO crawl contract services (sitemap, robots, prerender path registry)."""

from app.services.seo.crawl_policy import (
    fetch_sitemap_entries,
    list_disallow_prefixes,
    list_indexable_paths,
)
from app.services.seo.robots import build_robots_txt
from app.services.seo.site_url import absolute_url, get_site_url
from app.services.seo.sitemap_builder import build_sitemap_xml

__all__ = [
    "absolute_url",
    "build_robots_txt",
    "build_sitemap_xml",
    "fetch_sitemap_entries",
    "get_site_url",
    "list_disallow_prefixes",
    "list_indexable_paths",
]
