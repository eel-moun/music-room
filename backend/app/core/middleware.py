import time
import uuid

import structlog
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

log = structlog.get_logger()

QUIET_PATHS = {"/metrics", "/health"}  # polled every few seconds: no log line, no metrics
MAX_BODY_BYTES = 1_000_000


class RequestLogMiddleware:
    """One structured log line per request, with the device headers the subject asks for.

    Pure ASGI (not BaseHTTPMiddleware) so it shares `scope` with the route: the auth
    dependency stores the user id in `scope["state"]`, and we read it here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # Bound to the context: every log line written during this request carries them.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=uuid.uuid4().hex[:12],
            platform=headers.get("x-platform"),
            device=headers.get("x-device"),
            app_version=headers.get("x-app-version"),
        )

        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            await _reject(send, 413, b'{"detail":{"code":"payload_too_large"}}')
            return

        status = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope["path"]
            if path not in QUIET_PATHS:
                route = scope.get("route")
                # The template (/events/{event_id}), not the raw path: bounded label values.
                template = getattr(route, "path", "unmatched")
                elapsed = time.perf_counter() - start
                platform = headers.get("x-platform") or "unknown"
                HTTP_REQUESTS.labels(scope["method"], template, str(status), platform).inc()
                HTTP_LATENCY.labels(scope["method"], template).observe(elapsed)
                log.info(
                    "request",
                    method=scope["method"],
                    route=template,
                    path=path,
                    status=status,
                    duration_ms=round(elapsed * 1000, 1),
                    user_id=scope.get("state", {}).get("user_id"),
                    client_ip=scope["client"][0] if scope.get("client") else None,
                )
            structlog.contextvars.clear_contextvars()


async def _reject(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
