"""Production API middleware (Prompt 40 §8, §10, §26).

* CorrelationIdMiddleware — assigns/propagates an ``X-Request-ID`` per request,
  binds it to the logging ContextVar, and echoes it on the response so a workflow
  is traceable end-to-end.
* RequestSizeLimitMiddleware — rejects oversized request bodies (413) before they
  are read into memory.
* SecurityHeadersMiddleware — adds standard security headers (and HSTS only when
  explicitly enabled for HTTPS deployments).

These never expose secrets and never alter response bodies.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config.logging import get_request_id, reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and len(incoming) <= 64 else uuid.uuid4().hex
        token = set_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    return self._too_large()
            except ValueError:
                pass
        return await call_next(request)

    def _too_large(self) -> Response:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "request_too_large",
                               "message": f"Request body exceeds the {self.max_bytes}-byte limit.",
                               "request_id": get_request_id()}},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("X-XSS-Protection", "0")  # rely on CSP; disable legacy auditor
        # A conservative API CSP (this app's API returns JSON, not HTML pages).
        headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if self.hsts:
            headers.setdefault("Strict-Transport-Security",
                               "max-age=31536000; includeSubDomains")
        return response
