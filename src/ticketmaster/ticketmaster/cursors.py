import base64
import binascii
import json
from datetime import datetime
from decimal import Decimal
from typing import Self

from libs.common.schemas.dto import DTO

from ticketmaster.enums import EventSortKeyEnum


class EventCursorDTO(DTO):
    sort_key: EventSortKeyEnum
    sort_key_value: str | Decimal | datetime
    id: int

    def _base64_encode(self) -> str:
        raw = json.dumps(
            obj={"sort_key": self.sort_key, "sort_key_value": self.sort_key_value, "_id": self.id}
        ).encode()
        return base64.urlsafe_b64encode(s=raw).decode()

    @classmethod
    def _base64_decode(cls, cursor: str) -> Self:
        try:
            raw = base64.b64decode(s=cursor.encode(), altchars=b"-_", validate=True)
            payload = json.loads(raw)
            return cls(
                sort_key=payload["sort_key"],
                sort_key_value=str(payload["sort_key_value"]),
                id=int(payload["_id"]),
            )
        except binascii.Error, KeyError, TypeError, ValueError:
            raise ValueError("Invalid event cursor")

    @classmethod
    def _deserialize(cls, cursor: Self) -> Self:
        match cursor.sort_key:
            case EventSortKeyEnum.START_AT:
                sort_key_value = datetime.fromisoformat(cursor.sort_key_value)
            case EventSortKeyEnum.PRICE:
                sort_key_value = Decimal(cursor.sort_key_value)
            case _:
                raise ValueError(f"Unexpected cursor.sort_key, got {cursor.sort_key}")

        return cls(
            id=cursor.id,
            sort_key=cursor.sort_key,
            sort_key_value=sort_key_value,
        )

    def _serialize(self) -> Self:
        match self.sort_key:
            case EventSortKeyEnum.START_AT:
                sort_key_value = self.sort_key_value.isoformat()
            case EventSortKeyEnum.PRICE:
                sort_key_value = str(self.sort_key_value)
            case _:
                raise ValueError(f"Unexpected cursor.sort_key, got {self.sort_key}")

        return EventCursorDTO(
            id=self.id,
            sort_key=self.sort_key,
            sort_key_value=sort_key_value,
        )

    @classmethod
    def decode(cls, cursor: str) -> Self:
        base64_decoded = cls._base64_decode(cursor=cursor)
        return cls._deserialize(cursor=base64_decoded)

    def encode(self) -> str:
        serialized = self._serialize()
        return serialized._base64_encode()
