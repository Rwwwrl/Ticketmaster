from contextlib import suppress
from typing import Any

from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.admin.services.invalidate_event_cache_document_by_id import invalidate_event_cache_document_by_id
from ticketmaster.schemas.dtos import BaseEventDTO


async def update_event(session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
    dto = await AdminEventRepository.update(
        session=session,
        event_id=event_id,
        changes=changes,
    )

    with suppress(RedisError):
        await invalidate_event_cache_document_by_id(_id=event_id)

    return dto
