from datetime import datetime

from libs.fastapi_ext.schemas.base_schemas import BaseRequestSchema

from ticketmaster.enums import EventTypeEnum


class CreateEventRequestSchema(BaseRequestSchema):
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime


class UpdateEventRequestSchema(BaseRequestSchema):
    name: str | None = None
    description: str | None = None
    type: EventTypeEnum | None = None
    start_at: datetime | None = None
