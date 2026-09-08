from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

STATIC_MARKETING_PATHS: tuple[str, ...] = (
    "/",
    "/pricing",
    "/about",
    "/documentation",
    "/faq",
    "/contact",
    "/privacy",
    "/terms",
    "/request-trial",
)

DISALLOW_PREFIXES: tuple[str, ...] = (
    "/auth",
    "/portal",
    "/doctor-support",
    "/admin",
    "/v1/",
    "/health",
)

FORBIDDEN_INDEXABLE_FRAGMENTS: tuple[str, ...] = (
    "share",
    "/v1/",
    "/portal",
    "/admin",
    "/auth",
    "/doctor-support",
    "/encounter",
    "/customer",
)

_DOC_MANIFEST = Path(__file__).resolve().parents[2] / "data" / "seo" / "doc_manifest.json"


@dataclass(frozen=True)
class SitemapEntry:
    path: str
    lastmod: str


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


@lru_cache(maxsize=1)
def load_documentation_paths() -> tuple[str, ...]:
    data = json.loads(_DOC_MANIFEST.read_text(encoding="utf-8"))
    paths = data.get("documentation_paths", [])
    return tuple(_normalize_path(p) for p in paths)


@lru_cache(maxsize=1)
def _manifest_last_updated() -> str:
    data = json.loads(_DOC_MANIFEST.read_text(encoding="utf-8"))
    return str(data.get("last_updated", "2026-05-23"))


def list_disallow_prefixes() -> list[str]:
    return list(DISALLOW_PREFIXES)


def _path_disallowed_for_robots(path: str) -> bool:
    normalized = _normalize_path(path)
    for prefix in DISALLOW_PREFIXES:
        if prefix.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True
    return False


def _path_matches_forbidden_fragment(fragment: str, normalized: str) -> bool:
    """Segment-safe checks — avoid false positives (e.g. `/admin` inside `admins`)."""
    if fragment.startswith("/"):
        if fragment.endswith("/"):
            return normalized.startswith(fragment)
        return normalized == fragment or normalized.startswith(f"{fragment}/")
    return fragment in normalized


def _assert_paths_indexable(paths: list[str]) -> None:
    for path in paths:
        normalized = _normalize_path(path)
        for fragment in FORBIDDEN_INDEXABLE_FRAGMENTS:
            if _path_matches_forbidden_fragment(fragment, normalized):
                raise ValueError(
                    f"Indexable path {path!r} contains forbidden fragment {fragment!r}"
                )
        if _path_disallowed_for_robots(normalized):
            raise ValueError(f"Indexable path {path!r} is blocked by robots disallow rules")


def list_indexable_paths() -> list[str]:
    doc_paths = list(load_documentation_paths())
    combined = list(STATIC_MARKETING_PATHS) + doc_paths
    deduped = sorted(set(_normalize_path(p) for p in combined))
    _assert_paths_indexable(deduped)
    return deduped


def fetch_sitemap_entries() -> list[SitemapEntry]:
    lastmod = _manifest_last_updated()
    return [SitemapEntry(path=p, lastmod=lastmod) for p in list_indexable_paths()]


def paths_blocked_by_robots(paths: list[str]) -> list[str]:
    return [p for p in paths if _path_disallowed_for_robots(p)]
