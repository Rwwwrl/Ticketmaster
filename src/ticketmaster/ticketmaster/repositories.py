from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.models import Event
from ticketmaster.schemas.dtos import EventDTO


class EventRepository:
    @classmethod
    async def get_all(cls, session: AsyncSession) -> list[EventDTO]:
        result = await session.execute(select(Event))
        return [EventDTO.from_sqlmodel(event) for event in result.scalars().all()]
