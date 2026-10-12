import logging

from sqlalchemy.exc import DBAPIError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_logger = logging.getLogger("exception_handler.database")

_QUERY_CANCELED_SQLSTATE = "57014"
_CONNECTIVITY_SQLSTATES = frozenset({"57P01", "57P02", "57P03", "25006"})
_CONNECTION_EXCEPTION_SQLSTATE_CLASS = "08"


def _is_connectivity_error(exc: DBAPIError, sqlstate: str | None) -> bool:
    if exc.connection_invalidated:
        return True

    if sqlstate is None:
        return False

    return sqlstate in _CONNECTIVITY_SQLSTATES or sqlstate.startswith(_CONNECTION_EXCEPTION_SQLSTATE_CLASS)


async def database_exception_handler(request: Request, exc: DBAPIError) -> Response:
    sqlstate: str | None = getattr(exc.orig, "sqlstate", None)
    extra = {"http_method": request.method, "http_url": str(request.url), "sqlstate": sqlstate}

    if sqlstate == _QUERY_CANCELED_SQLSTATE:
        _logger.warning("Statement timeout on %s %s", request.method, request.url.path, extra=extra)
        return JSONResponse(
            status_code=504,
            content={"detail": "The server took too long to respond. Please retry later."},
        )

    if _is_connectivity_error(exc=exc, sqlstate=sqlstate):
        _logger.warning("Database unavailable on %s %s", request.method, request.url.path, extra=extra)
        return JSONResponse(
            status_code=503,
            content={"detail": "The service is temporarily unavailable. Please retry later."},
            headers={"Retry-After": "5"},
        )

    raise exc
