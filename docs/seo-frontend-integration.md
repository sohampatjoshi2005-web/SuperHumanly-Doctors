# SEO frontend integration (Phase 69)

Cross-repo contract between **healthcare-backend** v4.0 crawl APIs and **healthcare-frontend** v2.0 prerender.

## Endpoints (marketing / API host)

| Path | Consumer |
|------|----------|
| `GET /sitemap.xml` | Googlebot, GSC |
| `GET /robots.txt` | Googlebot |
| `GET /v1/seo/prerender-paths` | `scripts/prerender.mjs` at build time |

Response shape:

```json
{ "paths": ["/", "/pricing", "/documentation/getting-started/overview", "..."] }
```

Paths are the union of `STATIC_MARKETING_PATHS` and `app/data/seo/doc_manifest.json`.

## nginx (marketing origin)

```nginx
location = /sitemap.xml {
  proxy_pass http://api_upstream/sitemap.xml;
}
location = /robots.txt {
  proxy_pass http://api_upstream/robots.txt;
}
```

Frontend static root uses `try_files` for prerendered `dist/**/index.html` (see healthcare-frontend `nginx.conf`).

## Build-time env

| Variable | Default | Purpose |
|----------|---------|---------|
| `PRERENDER_API_URL` | `http://localhost:8000` | Fetch path list |
| `PRERENDER_SKIP` | unset | `1` skips Puppeteer in CI/Docker |
| `SITE_URL` / `VITE_SITE_URL` | — | Must match marketing canonical host |

## Parity tests

- Frontend: `src/seo/routes.contract.test.js`
- Backend: `tests/test_seo_crawl_policy.py`
- Verify: `healthcare-frontend/scripts/verify-phase20-crawl.mjs`
