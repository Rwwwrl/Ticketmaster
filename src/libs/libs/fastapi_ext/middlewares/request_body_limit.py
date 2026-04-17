import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE_BODY = json.dumps({"detail": "Request body too large"}).encode()


class _BodyTooLargeError(Exception):
    pass


def _get_content_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    for name, value in headers:
        if name.lower() == b"content-length":
            return int(value)
    return None


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": _TOO_LARGE_BODY,
        }
    )


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self._app = app
        self._max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_length = _get_content_length(headers=scope.get("headers", []))
        if content_length is not None and content_length > self._max_body_size:
            await _send_413(send=send)
            return

        bytes_received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal bytes_received

            message = await receive()

            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)

                if bytes_received > self._max_body_size:
                    raise _BodyTooLargeError

            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self._app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not response_started:
                await _send_413(send=send)
