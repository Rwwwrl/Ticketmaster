from datetime import datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.admin.repositories import AdminEventRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.services import EventService


class AdminEventService(EventService):
    @classmethod
    async def create_event(
        cls,
        session: AsyncSession,
        name: str,
        description: str,
        type: EventTypeEnum,
        start_at: datetime,
    ) -> BaseEventDTO:
        return await AdminEventRepository.create(
            session=session,
            name=name,
            description=description,
            type=type,
            start_at=start_at,
        )

    @classmethod
    async def update_event(cls, session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
        return await AdminEventRepository.update(session=session, event_id=event_id, changes=changes)
