import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_logger = logging.getLogger("middleware.request_response")

_SAFE_HEADERS: frozenset[str] = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "cache-control",
        "content-length",
        "content-type",
        "host",
        "origin",
        "referer",
        "traceparent",
        "tracestate",
        "user-agent",
        "x-amzn-trace-id",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-port",
        "x-forwarded-proto",
        "x-request-id",
    }
)

_SKIP_PATHS: frozenset[str] = frozenset({"/health", "/readiness_check", "/metrics", "/docs", "/redoc", "/openapi.json"})

_MAX_BODY_LOG_SIZE: int = 10_000


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: (value if key.lower() in _SAFE_HEADERS else "[REDACTED]") for key, value in headers.items()}


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start_time = time.monotonic()

        request_body = await request.body()
        request_body_str = request_body.decode("utf-8", errors="replace") if request_body else ""

        _logger.info(
            "Incoming request %s %s",
            request.method,
            request.url.path,
            extra={
                "http_method": request.method,
                "http_url": str(request.url),
                "http_headers": _sanitize_headers(dict(request.headers)),
                "http_body": request_body_str[:_MAX_BODY_LOG_SIZE],
            },
        )

        response = await call_next(request)

        response_body_parts: list[bytes] = []
        async for chunk in response.body_iterator:
            response_body_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())

        response_body = b"".join(response_body_parts)
        duration_ms = (time.monotonic() - start_time) * 1000

        _logger.info(
            "Response %s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "http_method": request.method,
                "http_url": str(request.url),
                "http_status": response.status_code,
                "http_duration_ms": round(duration_ms, 1),
                "http_response_body": response_body.decode("utf-8", errors="replace")[:_MAX_BODY_LOG_SIZE],
            },
        )

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
