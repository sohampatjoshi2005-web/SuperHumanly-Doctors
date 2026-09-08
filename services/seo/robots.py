from app.services.seo.crawl_policy import list_disallow_prefixes
from app.services.seo.site_url import get_site_url


def build_robots_txt() -> str:
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
    ]
    for prefix in list_disallow_prefixes():
        lines.append(f"Disallow: {prefix}")
    lines.extend(
        [
            "",
            f"Sitemap: {get_site_url()}/sitemap.xml",
            "",
        ]
    )
    return "\n".join(lines)
