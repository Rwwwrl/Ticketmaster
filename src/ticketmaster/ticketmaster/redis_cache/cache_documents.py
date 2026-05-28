from datetime import datetime
from typing import TYPE_CHECKING, Self

from libs.redis_ext import BaseCacheDocument

from ticketmaster.enums import EventTypeEnum

if TYPE_CHECKING:
    from ticketmaster.schemas.dtos import BaseEventDTO


class EventCacheDocument(BaseCacheDocument):
    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime

    @classmethod
    def from_dto(cls, dto: "BaseEventDTO") -> Self:
        return cls(**dto.model_dump())
