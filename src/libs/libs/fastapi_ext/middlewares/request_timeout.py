import asyncio
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, timeout_seconds: float) -> None:
        super().__init__(app)
        self._timeout_seconds = timeout_seconds

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout_seconds)
        except TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "Request timed out"})
