from fastapi import APIRouter
from starlette.responses import Response

from app.services.seo.robots import build_robots_txt
from app.services.seo.sitemap_builder import build_sitemap_xml

router = APIRouter(tags=["seo-crawl"])

CACHE_CONTROL = "public, max-age=3600"


@router.get("/sitemap.xml")
def sitemap_xml() -> Response:
    return Response(
        content=build_sitemap_xml(),
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": CACHE_CONTROL},
    )


@router.get("/robots.txt")
def robots_txt() -> Response:
    return Response(
        content=build_robots_txt(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": CACHE_CONTROL},
    )
