from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

DEV_FALLBACK = "http://localhost:5173"
_warned_dev_fallback = False


def is_production() -> bool:
    return settings.environment.lower() == "production"


def normalize_origin(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid SITE_URL (missing scheme or host): {url!r}")
    if parsed.path not in ("", "/"):
        raise ValueError(f"SITE_URL must not include a path: {url!r}")
    if parsed.query or parsed.fragment:
        raise ValueError(f"SITE_URL must not include query or fragment: {url!r}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin.rstrip("/")


def get_site_url() -> str:
    global _warned_dev_fallback
    raw = (settings.site_url or "").strip()

    if is_production():
        if not raw:
            raise ValueError(
                "SITE_URL is required in production (HTTPS marketing origin, no trailing slash)."
            )
        origin = normalize_origin(raw)
        if not origin.startswith("https://"):
            raise ValueError("SITE_URL must use https in production.")
        return origin

    if raw:
        try:
            return normalize_origin(raw)
        except ValueError as exc:
            logger.warning("Invalid SITE_URL in non-production: %s", exc)

    if not _warned_dev_fallback:
        logger.warning("SITE_URL unset; using dev fallback %s", DEV_FALLBACK)
        _warned_dev_fallback = True
    return DEV_FALLBACK


def absolute_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{get_site_url()}{path}"
