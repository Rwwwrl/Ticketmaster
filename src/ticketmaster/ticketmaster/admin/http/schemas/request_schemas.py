from datetime import datetime
from decimal import Decimal

from libs.fastapi_ext.schemas.base_schemas import BaseRequestSchema

from ticketmaster.enums import CurrencyEnum, EventTypeEnum


class CreateEventRequestSchema(BaseRequestSchema):
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime
    price: Decimal
    currency: CurrencyEnum


class UpdateEventRequestSchema(BaseRequestSchema):
    name: str = None
    description: str = None
    type: EventTypeEnum = None
    start_at: datetime = None
    price: Decimal = None
    currency: CurrencyEnum = None
