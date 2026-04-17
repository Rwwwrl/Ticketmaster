import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from libs.context_vars import request_id_var
from libs.fastapi_ext.consts import REQUEST_ID_HEADER

_MAX_REQUEST_ID_LENGTH = 256
_VALID_REQUEST_ID_PATTERN = re.compile(r"^[\x20-\x7E]+$")


def _is_valid_request_id(value: str) -> bool:
    return len(value) <= _MAX_REQUEST_ID_LENGTH and _VALID_REQUEST_ID_PATTERN.match(value) is not None


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER, None)

        if incoming_id and not _is_valid_request_id(value=incoming_id):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid X-Request-ID header"},
            )

        request_id = incoming_id or str(uuid.uuid4())

        request_id_var.set(request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
