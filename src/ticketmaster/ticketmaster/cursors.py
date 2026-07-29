from datetime import datetime
from decimal import Decimal
from typing import Any

from libs.common.schemas.base_db_cursor import BaseDBCursorDTO
from libs.common.schemas.base_service_cursor import BaseServiceCursorBodyDTO, BaseServiceCursorDTO
from libs.pydantic_ext.type_adapters import DATETIME_ADAPTER, DECIMAL_ADAPTER
from pydantic import model_validator

from ticketmaster.enums import EventSortKeyEnum


class EventDBCursorDTO(BaseDBCursorDTO):
    sort_key: EventSortKeyEnum
    sort_key_value: Decimal | datetime
    id: int


class EventCursorBodyDTO(BaseServiceCursorBodyDTO):
    sort_key: EventSortKeyEnum
    sort_key_value: Decimal | datetime
    id: int
    page_index: int

    @model_validator(mode="before")
    @classmethod
    def _deserialize_sort_key_value(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "sort_key" not in data or "sort_key_value" not in data:
            return data

        sort_key = EventSortKeyEnum(data["sort_key"])
        sort_key_value = data["sort_key_value"]

        match sort_key:
            case EventSortKeyEnum.START_AT:
                sort_key_value = DATETIME_ADAPTER.validate_python(sort_key_value)
            case EventSortKeyEnum.PRICE:
                sort_key_value = DECIMAL_ADAPTER.validate_python(sort_key_value)

        return {
            **data,
            "sort_key": sort_key,
            "sort_key_value": sort_key_value,
        }


class EventCursorDTO(BaseServiceCursorDTO):
    body: EventCursorBodyDTO
