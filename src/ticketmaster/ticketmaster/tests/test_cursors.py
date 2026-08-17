import base64
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from libs.common.services import create_service_cursor, decode_service_cursor, encode_service_cursor
from ticketmaster.cursors import EventCursorBodyDTO, EventCursorDTO
from ticketmaster.enums import EventSortKeyEnum

_SECRET = "cursor-test-secret"


@pytest.mark.parametrize(
    ("sort_key", "sort_key_value"),
    [
        (EventSortKeyEnum.START_AT, datetime(2026, 7, 1, tzinfo=UTC)),
        (EventSortKeyEnum.PRICE, Decimal("49.99")),
        (EventSortKeyEnum.RANK, 0.42),
    ],
)
def test_event_cursor_signed_round_trip(
    sort_key: EventSortKeyEnum,
    sort_key_value: datetime | Decimal | float,
) -> None:
    cursor = create_service_cursor(
        cursor_class=EventCursorDTO,
        body=EventCursorBodyDTO(
            sort_key=sort_key,
            sort_key_value=sort_key_value,
            id=42,
            page_index=3,
        ),
        secret=_SECRET,
    )

    decoded = decode_service_cursor(
        encoded_cursor=encode_service_cursor(cursor=cursor),
        cursor_class=EventCursorDTO,
        secret=_SECRET,
    )

    assert decoded.body.sort_key == sort_key
    assert decoded.body.sort_key_value == sort_key_value
    assert decoded.body.id == 42
    assert decoded.body.page_index == 3


@pytest.mark.parametrize("field", ["sort_key_value", "id", "page_index", "signature"])
def test_event_cursor_rejects_tampering(field: str) -> None:
    encoded = encode_service_cursor(
        cursor=create_service_cursor(
            cursor_class=EventCursorDTO,
            body=EventCursorBodyDTO(
                sort_key=EventSortKeyEnum.START_AT,
                sort_key_value=datetime(2026, 7, 1, tzinfo=UTC),
                id=42,
                page_index=2,
            ),
            secret=_SECRET,
        ),
    )
    payload = json.loads(base64.urlsafe_b64decode(encoded))
    if field == "signature":
        payload[field] = "tampered"
    else:
        payload["body"][field] = "tampered"
    tampered = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_service_cursor(
            encoded_cursor=tampered,
            cursor_class=EventCursorDTO,
            secret=_SECRET,
        )


def test_event_cursor_rejects_unsigned_cursor() -> None:
    unsigned_payload = {
        "body": {
            "sort_key": EventSortKeyEnum.START_AT,
            "sort_key_value": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
            "id": 42,
            "page_index": 1,
        },
    }
    unsigned = base64.urlsafe_b64encode(json.dumps(unsigned_payload).encode()).decode()

    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_service_cursor(
            encoded_cursor=unsigned,
            cursor_class=EventCursorDTO,
            secret=_SECRET,
        )


def test_event_cursor_rejects_different_secret() -> None:
    encoded = encode_service_cursor(
        cursor=create_service_cursor(
            cursor_class=EventCursorDTO,
            body=EventCursorBodyDTO(
                sort_key=EventSortKeyEnum.PRICE,
                sort_key_value=Decimal("49.99"),
                id=42,
                page_index=1,
            ),
            secret=_SECRET,
        ),
    )

    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_service_cursor(
            encoded_cursor=encoded,
            cursor_class=EventCursorDTO,
            secret="different-secret",
        )
