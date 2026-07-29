from contextlib import suppress
from typing import Any

from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.redis_cache.utils import rotate_service_redis_cache_namespace
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.schemas.dtos import BaseEventDTO


async def update_event(session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
    event = await AdminEventRepository.get_for_update(session=session, _id=event_id)

    dto = await AdminEventRepository.update(
        session=session,
        _id=event.id,
        changes=changes,
    )

    # NOTE @sosov: Namespace rotation happens before the surrounding transaction commits. Moving
    # cache invalidation after commit is tracked separately.
    with suppress(RedisError):
        await rotate_service_redis_cache_namespace()

    return dto
