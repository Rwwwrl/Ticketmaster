from datetime import datetime
from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.schemas.dtos import BaseEventDTO


async def create_event(
    session: AsyncSession,
    name: str,
    description: str,
    type: EventTypeEnum,
    start_at: datetime,
    price: Decimal,
    currency: CurrencyEnum,
) -> BaseEventDTO:
    return await AdminEventRepository.create(
        session=session,
        name=name,
        description=description,
        type=type,
        start_at=start_at,
        price=price,
        currency=currency,
    )
