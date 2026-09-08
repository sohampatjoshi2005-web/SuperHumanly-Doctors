from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ApiNoIndexMiddleware(BaseHTTPMiddleware):
    """Belt-and-suspenders: discourage indexing of JSON API responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/v1/") or path == "/v1":
            response.headers["X-Robots-Tag"] = "noindex"
        return response
