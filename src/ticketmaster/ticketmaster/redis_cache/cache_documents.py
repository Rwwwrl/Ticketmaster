from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Self

from libs.redis_ext import BaseCacheDocument

from ticketmaster.enums import CurrencyEnum, EventTypeEnum

if TYPE_CHECKING:
    from ticketmaster.schemas.dtos import BaseEventDTO


class EventCacheDocument(BaseCacheDocument):
    version: ClassVar[int] = 1

    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime
    price: Decimal
    currency: CurrencyEnum

    @classmethod
    def from_dto(cls, dto: "BaseEventDTO") -> Self:
        return cls(**dto.model_dump())
