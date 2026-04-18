from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.models import Event
from ticketmaster.schemas.dtos import EventDTO


class EventRepository:
    @classmethod
    async def get_all(cls, session: AsyncSession) -> list[EventDTO]:
        result = await session.exec(select(Event))
        return [EventDTO.from_sqlmodel(event) for event in result.all()]
