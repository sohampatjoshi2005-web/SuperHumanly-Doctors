# Environment schema — healthcare-backend (SEO v4.0)

## SEO & crawl

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SITE_URL` | **Yes in production** | `""` (dev falls back to `http://localhost:5173` in SEO services) | Canonical marketing origin: `https://superhumanlymedical.io` — no trailing slash |
| `ENVIRONMENT` | No | `development` | `production` enables OpenAPI lockdown and requires `SITE_URL` in `validate_settings()` |

## Marketing nginx (production)

Proxy on the **marketing host** (same origin as `SITE_URL`):

```nginx
location = /sitemap.xml {
  proxy_pass http://api_upstream/sitemap.xml;
}
location = /robots.txt {
  proxy_pass http://api_upstream/robots.txt;
}
```

Frontend `prerender.mjs` (Phase 24) fetches:

```
GET {PRERENDER_API_URL}/v1/seo/prerender-paths
```

Default `PRERENDER_API_URL`: `http://localhost:8000` at build time.

## Verification

```bash
./scripts/verify-seo-crawl.sh
```
