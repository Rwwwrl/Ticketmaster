import logging
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_logger = logging.getLogger("middleware.unhandled_exception")


class UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            _logger.exception(
                "Unhandled exception on %s %s",
                request.method,
                request.url.path,
                extra={
                    "http_method": request.method,
                    "http_url": str(request.url),
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )
