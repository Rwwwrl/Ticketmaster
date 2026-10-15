import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from libs.context_vars import request_id_var
from libs.fastapi_ext.consts import REQUEST_ID_HEADER


def _parse_request_id(value: str) -> str | None:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER, None)

        if incoming_id:
            request_id = _parse_request_id(value=incoming_id)
            if request_id is None:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid X-Request-ID header"},
                )
        else:
            request_id = str(uuid.uuid4())

        request_id_var.set(request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
