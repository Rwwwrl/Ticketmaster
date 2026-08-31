from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from libs.common.schemas.dto import DTO

from ticketmaster.enums import CurrencyEnum, EventTypeEnum, TicketStatusEnum
from ticketmaster.models import Event, Ticket, User
from ticketmaster.redis_cache.cache_documents import EventCacheDocument


class BaseEventDTO(DTO):
    id: int
    logical_identity: UUID
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime
    price: Decimal
    currency: CurrencyEnum

    @classmethod
    def from_sqlmodel(cls, model: Event) -> Self:
        return cls(**model.model_dump())

    @classmethod
    def from_cache_document(cls, document: EventCacheDocument) -> Self:
        return cls(**document.model_dump())


class BaseTicketDTO(DTO):
    id: int
    event_id: int
    user_id: int | None
    status: TicketStatusEnum
    reserved_at: datetime | None
    booked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_sqlmodel(cls, model: Ticket) -> Self:
        return cls(**model.model_dump())


class BaseUserDTO(DTO):
    id: int
    uuid: UUID
    pool_id: str
    email: str
    cognito_username: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_sqlmodel(cls, model: User) -> Self:
        return cls(**model.model_dump())
