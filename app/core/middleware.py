"""
ASGI middleware for Prometheus request metrics and request-id propagation.
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL
from app.core.logging import request_id_ctx


def _normalise_path(path: str) -> str:
    """Collapse numeric path segments to keep cardinality low.

    /api/evidence/42       -> /api/evidence/{id}
    /api/risk/workflow/7   -> /api/risk/workflow/{id}
    """
    parts = path.rstrip("/").split("/")
    return "/".join("{id}" if p.isdigit() else p for p in parts) or "/"


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Measure HTTP request duration and count, expose via Prometheus."""

    async def dispatch(self, request: Request, call_next):
        # Propagate or generate request_id
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)

        # Skip metrics endpoint itself to avoid self-instrumentation
        if request.url.path == "/metrics":
            response = await call_next(request)
            request_id_ctx.reset(token)
            return response

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start

        path = _normalise_path(request.url.path)
        method = request.method
        status = str(response.status_code)

        HTTP_REQUEST_DURATION.labels(method=method, path=path, status_code=status).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status).inc()

        # Echo request_id back in response header
        response.headers["X-Request-ID"] = rid

        request_id_ctx.reset(token)
        return response
