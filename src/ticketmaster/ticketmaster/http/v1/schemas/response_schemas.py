from datetime import datetime
from uuid import UUID

from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema

from ticketmaster.enums import EventTypeEnum


class EventResponseSchema(BaseResponseSchema):
    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime


class EventsPageResponseSchema(BaseResponseSchema):
    items: list[EventResponseSchema]
    page_size: int
    next_cursor: str | None


class UserResponseSchema(BaseResponseSchema):
    uuid: UUID
    pool_id: str
    email: str
    cognito_username: str
    created_at: datetime
    updated_at: datetime
