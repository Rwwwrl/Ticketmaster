from datetime import datetime

from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema

from ticketmaster.enums import EventTypeEnum


class EventResponseSchema(BaseResponseSchema):
    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime
