from contextlib import suppress
from typing import Any

from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.redis_cache.utils import invalidate_event_cache_document_by_id, rotate_service_cache_namespace
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.schemas.dtos import BaseEventDTO


async def update_event(session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
    dto = await AdminEventRepository.update(
        session=session,
        event_id=event_id,
        changes=changes,
    )

    # NOTE @sosov: Namespace rotation happens before the surrounding transaction commits. Moving
    # cache invalidation after commit is tracked separately.
    with suppress(RedisError):
        await rotate_service_cache_namespace()

    with suppress(RedisError):
        await invalidate_event_cache_document_by_id(_id=event_id)

    return dto
