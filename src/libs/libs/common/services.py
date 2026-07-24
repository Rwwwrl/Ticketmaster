import base64
import binascii
import hashlib
import hmac
import json
from typing import Any, TypeVar

from libs.common.schemas.base_service_cursor import BaseServiceCursorBodyDTO, BaseServiceCursorDTO
from libs.common.utils import dumps_to_canonical_json

_ServiceCursorT = TypeVar("_ServiceCursorT", bound=BaseServiceCursorDTO)


def create_service_cursor(
    cursor_class: type[_ServiceCursorT],
    body: BaseServiceCursorBodyDTO,
    secret: str,
) -> _ServiceCursorT:
    serialized_body = body.model_dump(mode="json")
    signature = sign_cursor_body(body=serialized_body, secret=secret)
    return cursor_class.model_validate(
        {
            "body": body,
            "signature": signature,
        },
    )


def sign_cursor_body(body: dict[str, Any], secret: str) -> str:
    signature = hmac.new(
        key=secret.encode(),
        msg=dumps_to_canonical_json(obj=body),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")


def encode_service_cursor(cursor: BaseServiceCursorDTO) -> str:
    serialized = cursor.model_dump(mode="json")
    return base64.urlsafe_b64encode(dumps_to_canonical_json(obj=serialized)).decode("utf-8")


def decode_service_cursor(
    encoded_cursor: str,
    cursor_class: type[_ServiceCursorT],
    secret: str,
) -> _ServiceCursorT:
    try:
        raw = base64.b64decode(s=encoded_cursor.encode(), altchars=b"-_", validate=True)

        decoded = json.loads(raw)

        if not isinstance(decoded, dict):
            raise TypeError("Cursor must contain a JSON object")

        body = decoded["body"]
        signature = decoded["signature"]

        if not isinstance(body, dict) or not isinstance(signature, str):
            raise TypeError("Invalid cursor payload")

        expected_signature = sign_cursor_body(body=body, secret=secret)
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Invalid cursor signature")

        return cursor_class.model_validate(decoded)

    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid cursor: {exc}") from exc
