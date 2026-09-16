#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ENVIRONMENT="${ENVIRONMENT:-development}"
export SITE_URL="${SITE_URL:-https://superhumanlymedical.io}"

echo "== SEO unit tests =="
python3 -m pytest tests/test_seo_site_url.py tests/test_seo_crawl_policy.py tests/test_seo_sitemap_robots.py tests/test_seo_http_routes.py -q --tb=short

echo "== SEO HTTP smoke (TestClient) =="
python3 -m pytest tests/test_seo_production_hardening.py -q --tb=short 2>/dev/null || true

if [[ "${VERIFY_SKIP_HTTP:-}" == "1" ]]; then
  echo "VERIFY_SKIP_HTTP=1 — skipping live curl checks"
  exit 0
fi

API_BASE="${SEO_API_BASE:-http://localhost:8000}"
echo "== Live crawl endpoints at ${API_BASE} =="

curl -fsS "${API_BASE}/sitemap.xml" | head -c 200
echo ""
curl -fsS "${API_BASE}/robots.txt" | head -c 200
echo ""
curl -fsS "${API_BASE}/v1/seo/prerender-paths" | head -c 200
echo ""
echo "verify-seo-crawl: OK"
