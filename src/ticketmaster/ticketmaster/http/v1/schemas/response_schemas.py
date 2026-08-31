from datetime import datetime
from decimal import Decimal
from uuid import UUID

from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema

from ticketmaster.enums import CurrencyEnum, EventTypeEnum, TicketStatusEnum


class EventResponseSchema(BaseResponseSchema):
    id: int
    logical_identity: UUID
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime
    price: Decimal
    currency: CurrencyEnum


class EventsPageResponseSchema(BaseResponseSchema):
    items: list[EventResponseSchema]
    page_size: int
    next_cursor: str | None


class TicketResponseSchema(BaseResponseSchema):
    id: int
    event_id: int
    status: TicketStatusEnum
    reserved_at: datetime | None
    booked_at: datetime | None


class UserResponseSchema(BaseResponseSchema):
    uuid: UUID
    pool_id: str
    email: str
    cognito_username: str
    created_at: datetime
    updated_at: datetime
