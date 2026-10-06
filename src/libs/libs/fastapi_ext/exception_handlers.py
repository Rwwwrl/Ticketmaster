import logging

from sqlalchemy.exc import DBAPIError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_logger = logging.getLogger("exception_handler.statement_timeout")

_QUERY_CANCELED_SQLSTATE = "57014"


async def statement_timeout_exception_handler(request: Request, exc: DBAPIError) -> Response:
    if getattr(exc.orig, "sqlstate", None) != _QUERY_CANCELED_SQLSTATE:
        raise exc

    _logger.warning(
        "Statement timeout on %s %s",
        request.method,
        request.url.path,
        extra={"http_method": request.method, "http_url": str(request.url)},
    )
    return JSONResponse(status_code=504, content={"detail": "The server took too long to respond. Please retry later."})
