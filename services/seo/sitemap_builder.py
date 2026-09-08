from xml.etree import ElementTree as ET

from app.services.seo.crawl_policy import fetch_sitemap_entries
from app.services.seo.site_url import absolute_url

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def build_sitemap_xml() -> str:
    urlset = ET.Element("urlset", xmlns=SITEMAP_NS)
    for entry in fetch_sitemap_entries():
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc")
        loc.text = absolute_url(entry.path)
        lastmod = ET.SubElement(url_el, "lastmod")
        lastmod.text = entry.lastmod

    xml_body = ET.tostring(urlset, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
