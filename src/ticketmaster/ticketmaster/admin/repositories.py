from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from libs.datetime_ext.utils import utc_now
from sqlalchemy import delete
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.exceptions import EventNotFoundException
from ticketmaster.models import Event, Ticket
from ticketmaster.repositories import EventRepository, TicketRepository
from ticketmaster.schemas.dtos import BaseEventDTO


class AdminEventRepository(EventRepository):
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        logical_identity: UUID,
        name: str,
        description: str,
        type: EventTypeEnum,
        start_at: datetime,
        price: Decimal,
        currency: CurrencyEnum,
    ) -> BaseEventDTO:
        event = Event(
            logical_identity=logical_identity,
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
    async def get_for_update(cls, session: AsyncSession, _id: int) -> Event:
        result = await session.exec(select(Event).where(Event.id == _id).with_for_update())
        event = result.first()

        if event is None:
            raise EventNotFoundException(f"Event not found for id={_id}")

        return event

    @classmethod
    async def update(cls, session: AsyncSession, _id: int, changes: dict[str, Any]) -> BaseEventDTO:
        result = await session.exec(select(Event).where(Event.id == _id))
        event = result.first()

        if event is None:
            raise EventNotFoundException(f"Event not found for id={_id}")

        event.sqlmodel_update(changes)
        event.updated_at = utc_now()
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return BaseEventDTO.from_sqlmodel(model=event)

    @classmethod
    async def delete(cls, session: AsyncSession, _id: int) -> None:
        await session.exec(delete(Event).where(Event.id == _id))


class AdminTicketRepository(TicketRepository):
    @classmethod
    async def exists(cls, session: AsyncSession, event_id: int | None = None) -> bool:
        filters: list[ColumnElement[bool]] = []

        if event_id is not None:
            filters.append(Ticket.event_id == event_id)

        result = await session.exec(select(Ticket.id).where(*filters).limit(1))

        return result.first() is not None
