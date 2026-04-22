from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.models import Event
from ticketmaster.schemas.dtos import EventDTO


class EventRepository:
    @classmethod
    async def get_all_paginated(
        cls,
        session: AsyncSession,
        page: int,
        page_size: int,
    ) -> tuple[list[EventDTO], int]:
        """Return a slice of events for the requested page together with the total row count.

        Ordered by (start_at, id) ASC so pages are stable across requests.
        The total is returned alongside the items so the caller can expose page metadata
        without issuing a second query.
        """
        offset = (page - 1) * page_size
        items_result = await session.exec(
            select(Event).order_by(Event.start_at, Event.id).offset(offset).limit(page_size)
        )
        items = [EventDTO.from_sqlmodel(model=event) for event in items_result.all()]

        total_result = await session.exec(select(func.count(Event.id)))
        total = total_result.one()

        return items, total
