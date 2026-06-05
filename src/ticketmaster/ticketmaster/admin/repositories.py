from datetime import datetime
from decimal import Decimal
from typing import Any

from libs.datetime_ext.utils import utc_now
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.exceptions import EventNotFoundException
from ticketmaster.models import Event
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO


class AdminEventRepository(EventRepository):
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        name: str,
        description: str,
        type: EventTypeEnum,
        start_at: datetime,
        price: Decimal,
        currency: CurrencyEnum,
    ) -> BaseEventDTO:
        event = Event(
            name=name,
            description=description,
            type=type,
            start_at=start_at,
            price=price,
            currency=currency,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return BaseEventDTO.from_sqlmodel(model=event)

    @classmethod
    async def update(cls, session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
        result = await session.exec(select(Event).where(Event.id == event_id))
        event = result.first()

        if event is None:
            raise EventNotFoundException(f"Event not found for id={event_id}")

        event.sqlmodel_update(changes)
        event.updated_at = utc_now()
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return BaseEventDTO.from_sqlmodel(model=event)
