from fastapi import APIRouter

from app.services.seo.crawl_policy import list_indexable_paths

router = APIRouter(prefix="/seo", tags=["seo"])


@router.get("/prerender-paths")
def prerender_paths() -> dict[str, list[str]]:
    return {"paths": list_indexable_paths()}
