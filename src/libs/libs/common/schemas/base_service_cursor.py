from enum import Enum
from typing import Any

from libs.common.schemas.dto import DTO


class BaseServiceCursorBodyDTO(DTO):
    sort_key: Enum
    sort_key_value: Any
    id: int
    page_index: int


class BaseServiceCursorDTO(DTO):
    body: BaseServiceCursorBodyDTO
    signature: str
